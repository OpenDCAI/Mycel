"""MessagingService — core business logic for the messaging module.

Wraps Supabase messaging repos with business rules:
- create_chat, find_or_create_chat
- send (with delivery routing)
- retract, delete_for, mark_read
- list_messages, list_chats
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Any

from backend.web.utils.serializers import avatar_url
from messaging.contracts import ContentType, MessageType
from messaging.display_user import resolve_messaging_display_user

logger = logging.getLogger(__name__)


class MessagingService:
    """Core messaging operations backed by Supabase repos."""

    def __init__(
        self,
        chat_repo: Any,  # chat repo compatible with MessagingService create/list/delete operations
        chat_member_repo: Any,  # SupabaseChatMemberRepo or compatible
        messages_repo: Any,  # SupabaseMessagesRepo
        message_read_repo: Any,  # SupabaseMessageReadRepo
        user_repo: Any,  # UserRepo (for name + avatar lookup)
        thread_repo: Any | None = None,
        delivery_resolver: Any | None = None,
        delivery_fn: Callable | None = None,
        event_bus: Any | None = None,  # ChatEventBus-compatible publisher (optional)
    ) -> None:
        self._chats = chat_repo
        self._members_repo = chat_member_repo
        self._messages = messages_repo
        self._user_repo = user_repo
        self._delivery_resolver = delivery_resolver
        self._delivery_fn = delivery_fn
        self._event_bus = event_bus
        self._reads = message_read_repo

    def _normalize_message_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            **row,
            "sender_id": row.get("sender_id") or row.get("sender_user_id"),
            "mentioned_ids": row.get("mentioned_ids") or row.get("mentions") or row.get("mentions_json") or [],
            "reply_to": row.get("reply_to") or row.get("reply_to_message_id"),
            "ai_metadata": row.get("ai_metadata") or row.get("ai_metadata_json") or {},
        }

    def _project_message_response(self, row: dict[str, Any]) -> dict[str, Any]:
        # @@@message-response-projection - public chat message payload must keep
        # sender projection ownership in MessagingService so route send/list stay thin.
        message = self._normalize_message_row(row)
        sender = self._resolve_display_user(message.get("sender_id", ""))
        return {
            "id": message["id"],
            "chat_id": message["chat_id"],
            "sender_id": message.get("sender_id"),
            "sender_name": sender.display_name if sender else "unknown",
            "content": message["content"],
            "message_type": message.get("message_type", "human"),
            "mentioned_ids": message.get("mentioned_ids") or [],
            "signal": message.get("signal"),
            "retracted_at": message.get("retracted_at"),
            "created_at": message.get("created_at"),
        }

    def _resolve_display_user(self, social_user_id: str) -> Any | None:
        return resolve_messaging_display_user(
            user_repo=self._user_repo,
            social_user_id=social_user_id,
        )

    def resolve_display_user(self, social_user_id: str) -> Any | None:
        return self._resolve_display_user(social_user_id)

    def project_message_response(self, row: dict[str, Any]) -> dict[str, Any]:
        return self._project_message_response(row)

    def _build_chat_entities(self, chat_id: str) -> list[dict[str, Any]]:
        entities_info = []
        for member in self._members_repo.list_members(chat_id):
            social_user_id = member.get("user_id")
            entity = self._resolve_display_user(social_user_id) if social_user_id else None
            if entity is None:
                continue
            # @@@thread-social-entity-projection - outward chat entities must keep the
            # social/thread user id while borrowing display/avatar fields from the resolved user row.
            entities_info.append(
                {
                    "id": social_user_id,
                    "name": entity.display_name,
                    "type": entity.type.value if hasattr(entity.type, "value") else str(entity.type),
                    "avatar_url": avatar_url(entity.id, bool(entity.avatar)),
                }
            )
        return entities_info

    def set_delivery_fn(self, fn: Callable) -> None:
        self._delivery_fn = fn

    # ------------------------------------------------------------------
    # Chat lifecycle
    # ------------------------------------------------------------------

    def find_or_create_chat(self, user_ids: list[str], title: str | None = None) -> dict[str, Any]:
        if len(user_ids) != 2:
            raise ValueError("Use create_group_chat() for 3+ users")
        existing_id = self._members_repo.find_chat_between(user_ids[0], user_ids[1])
        if existing_id:
            chat = self._chats.get_by_id(existing_id)
            return {"id": chat.id, "title": chat.title, "status": chat.status, "created_at": chat.created_at}

        return self._create_chat(user_ids, chat_type="direct", title=title)

    def create_group_chat(self, user_ids: list[str], title: str | None = None) -> dict[str, Any]:
        if len(user_ids) < 3:
            raise ValueError("Group chat requires 3+ users")
        return self._create_chat(user_ids, chat_type="group", title=title)

    def _create_chat(self, user_ids: list[str], *, chat_type: str, title: str | None) -> dict[str, Any]:
        from storage.contracts import ChatRow

        chat_id = str(uuid.uuid4())
        now = time.time()
        self._chats.create(
            ChatRow(
                id=chat_id,
                type=chat_type,
                created_by_user_id=user_ids[0],
                title=title,
                status="active",
                created_at=now,
            )
        )
        for uid in user_ids:
            self._members_repo.add_member(chat_id, uid)
        return {"id": chat_id, "title": title, "status": "active", "created_at": now}

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send(
        self,
        chat_id: str,
        sender_id: str,
        content: str,
        *,
        message_type: MessageType = "human",
        content_type: ContentType = "text",
        mentions: list[str] | None = None,
        signal: str | None = None,
        reply_to: str | None = None,
        ai_metadata: dict[str, Any] | None = None,
        enforce_caught_up: bool = False,
    ) -> dict[str, Any]:
        msg_id = str(uuid.uuid4())

        row: dict[str, Any] = {
            "id": msg_id,
            "chat_id": chat_id,
            "sender_user_id": sender_id,
            "content": content,
            "content_type": content_type,
            "message_type": message_type,
            "mentions_json": mentions or [],
            "created_at": time.time(),
        }
        if signal in ("open", "yield", "close"):
            row["signal"] = signal
        if reply_to:
            row["reply_to_message_id"] = reply_to
        if ai_metadata:
            row["ai_metadata_json"] = ai_metadata

        if enforce_caught_up:
            last_read_seq = getattr(self._members_repo, "last_read_seq", None)
            if last_read_seq is None:
                raise RuntimeError("chat_member_repo must expose last_read_seq for caught-up sends")
            created_row = self._messages.create(row, expected_read_seq=int(last_read_seq(chat_id, sender_id)))
        else:
            created_row = self._messages.create(row)
        created = self._normalize_message_row(created_row)
        logger.debug("[messaging] send chat=%s sender=%s msg=%s type=%s", chat_id[:8], sender_id[:15], msg_id[:8], message_type)

        # Publish to event bus (SSE / Realtime bridge)
        if self._event_bus:
            self._event_bus.publish(
                chat_id,
                {
                    "event": "message",
                    "data": self._project_message_response(created),
                },
            )

        # Deliver to agent recipients
        if message_type in ("human", "ai"):
            self._deliver_to_agents(chat_id, sender_id, content, mentions or [], signal=signal)

        return created

    def _deliver_to_agents(
        self,
        chat_id: str,
        sender_id: str,
        content: str,
        mentions: list[str],
        signal: str | None = None,
    ) -> None:
        mention_set = set(mentions)
        members = self._members_repo.list_members(chat_id)
        sender_user = self._resolve_display_user(sender_id)
        sender_name = sender_user.display_name if sender_user else "unknown"
        sender_avatar_url = avatar_url(sender_user.id if sender_user else sender_id, bool(sender_user.avatar if sender_user else None))
        sender_raw_type = getattr(sender_user, "type", None) if sender_user else None
        sender_type = sender_raw_type.value if isinstance(sender_raw_type, Enum) else sender_raw_type
        sender_owner_id = sender_user.id if sender_user and sender_type == "human" else getattr(sender_user, "owner_user_id", None)

        for member in members:
            uid = member.get("user_id")
            if not uid or uid == sender_id:
                continue
            m = self._resolve_display_user(uid)
            if not m:
                continue
            member_raw_type = getattr(m, "type", None)
            member_type = member_raw_type.value if isinstance(member_raw_type, Enum) else member_raw_type
            if member_type == "human":
                continue

            # @@@same-owner-group-delivery - explicit group membership among the same owner
            # must reach sibling actors even when no relationship row exists yet.
            if sender_owner_id and getattr(m, "owner_user_id", None) == sender_owner_id:
                if self._delivery_fn:
                    try:
                        self._delivery_fn(uid, m, content, sender_name, chat_id, sender_id, sender_avatar_url, signal=signal)
                    except Exception:
                        logger.exception("[messaging] delivery failed for member %s", uid)
                continue

            from messaging.delivery.actions import DeliveryAction

            if self._delivery_resolver:
                is_mentioned = uid in mention_set
                action = self._delivery_resolver.resolve(uid, chat_id, sender_id, is_mentioned=is_mentioned)
                if action != DeliveryAction.DELIVER:
                    logger.info("[messaging] POLICY %s for %s", action.value, uid[:15])
                    continue

            if self._delivery_fn:
                try:
                    self._delivery_fn(uid, m, content, sender_name, chat_id, sender_id, sender_avatar_url, signal=signal)
                except Exception:
                    logger.exception("[messaging] delivery failed for member %s", uid)

    # ------------------------------------------------------------------
    # Lifecycle operations
    # ------------------------------------------------------------------

    def retract(self, message_id: str, sender_id: str) -> bool:
        return self._messages.retract(message_id, sender_id)

    def delete_for(self, message_id: str, user_id: str) -> None:
        self._messages.delete_for(message_id, user_id)

    def mark_read(self, chat_id: str, user_id: str) -> None:
        """Mark all messages in a chat as read for user."""
        msgs = self._messages.list_by_chat(chat_id, limit=1, viewer_id=user_id)
        last_read_seq = int(msgs[-1].get("seq") or 0) if msgs else 0
        self._members_repo.update_last_read(chat_id, user_id, last_read_seq)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_messages(
        self, chat_id: str, *, limit: int = 50, before: str | None = None, viewer_id: str | None = None
    ) -> list[dict[str, Any]]:
        rows = self._messages.list_by_chat(
            chat_id,
            limit=limit,
            before=before,
            viewer_id=viewer_id,
        )
        return [self._normalize_message_row(row) for row in rows]

    def list_message_responses(
        self, chat_id: str, *, limit: int = 50, before: str | None = None, viewer_id: str | None = None
    ) -> list[dict[str, Any]]:
        rows = self._messages.list_by_chat(
            chat_id,
            limit=limit,
            before=before,
            viewer_id=viewer_id,
        )
        return [self._project_message_response(row) for row in rows]

    def list_unread(self, chat_id: str, user_id: str) -> list[dict[str, Any]]:
        return [self._normalize_message_row(row) for row in self._messages.list_unread(chat_id, user_id)]

    def count_unread(self, chat_id: str, user_id: str) -> int:
        return self._messages.count_unread(chat_id, user_id)

    def find_direct_chat_id(self, actor_id: str, target_id: str) -> str | None:
        return self._members_repo.find_chat_between(actor_id, target_id)

    def search_messages(self, query: str, *, chat_id: str | None = None) -> list[dict[str, Any]]:
        return self._messages.search(query, chat_id=chat_id)

    def list_chat_members(self, chat_id: str) -> list[dict[str, Any]]:
        return self._members_repo.list_members(chat_id)

    def is_chat_member(self, chat_id: str, user_id: str) -> bool:
        return self._members_repo.is_member(chat_id, user_id)

    def list_messages_by_time_range(
        self,
        chat_id: str,
        *,
        after: str | None = None,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._messages.list_by_time_range(chat_id, after=after, before=before)
        return [self._normalize_message_row(row) for row in rows]

    def update_mute(self, chat_id: str, user_id: str, muted: bool, mute_until: str | None) -> None:
        self._members_repo.update_mute(chat_id, user_id, muted, mute_until)

    def get_chat_detail(self, chat: Any) -> dict[str, Any]:
        return {
            "id": chat.id,
            "title": chat.title,
            "status": chat.status,
            "created_at": chat.created_at,
            "entities": self._build_chat_entities(chat.id),
        }

    def list_chats_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """List all active chats for user with summary info."""
        chat_rows, members_by_chat, users_by_id, unread_by_chat = self._chat_projection_inputs(user_id)
        latest_messages = self._messages.list_latest_by_chat_ids([chat.id for chat in chat_rows])
        latest_sender_ids: set[str] = set()
        for row in latest_messages.values():
            sender_id = str(self._normalize_message_row(row).get("sender_id") or "")
            if sender_id:
                latest_sender_ids.add(sender_id)
        missing_sender_ids = sorted(latest_sender_ids - set(users_by_id))
        users_by_id.update(self._users_by_id(missing_sender_ids))

        result: list[dict[str, Any]] = []
        for chat in chat_rows:
            entities_info = self._project_chat_entities(members_by_chat[chat.id], users_by_id)
            title, chat_avatar_url = self._chat_title_and_avatar(chat.title, entities_info, user_id)
            result.append(
                {
                    "id": chat.id,
                    "title": title,
                    "status": chat.status,
                    "created_at": chat.created_at,
                    "updated_at": getattr(chat, "updated_at", None) or getattr(chat, "created_at", None),
                    "avatar_url": chat_avatar_url,
                    "entities": entities_info,
                    "last_message": self._project_latest_message(latest_messages.get(chat.id), users_by_id),
                    "unread_count": int(unread_by_chat.get(chat.id, 0)),
                    "has_mention": False,  # TODO: implement mention tracking
                }
            )
        return result

    def list_conversation_summaries_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """List lightweight visit-chat rows for the global conversation sidebar."""
        chat_rows, members_by_chat, users_by_id, unread_by_chat = self._chat_projection_inputs(user_id)
        result: list[dict[str, Any]] = []
        for chat in chat_rows:
            entities_info = self._project_chat_entities(members_by_chat[chat.id], users_by_id)
            title, chat_avatar_url = self._chat_title_and_avatar(chat.title, entities_info, user_id)
            result.append(
                {
                    "id": chat.id,
                    "title": title,
                    "updated_at": getattr(chat, "updated_at", None) or getattr(chat, "created_at", None),
                    "avatar_url": chat_avatar_url,
                    "unread_count": int(unread_by_chat.get(chat.id, 0)),
                }
            )
        return result

    def _chat_projection_inputs(
        self,
        user_id: str,
    ) -> tuple[list[Any], dict[str, list[dict[str, Any]]], dict[str, Any], dict[str, int]]:
        chat_ids = self._members_repo.list_chats_for_user(user_id)
        if not chat_ids:
            return [], {}, {}, {}

        chat_rows = [chat for chat in self._chats.list_by_ids(chat_ids) if chat.status == "active"]
        active_chat_ids = [chat.id for chat in chat_rows]
        if not active_chat_ids:
            return [], {}, {}, {}

        members_by_chat: dict[str, list[dict[str, Any]]] = {chat_id: [] for chat_id in active_chat_ids}
        last_read_by_chat: dict[str, int] = {}
        for member in self._members_repo.list_members_for_chats(active_chat_ids):
            chat_id = str(member.get("chat_id") or "")
            if chat_id not in members_by_chat:
                continue
            members_by_chat[chat_id].append(member)
            if member.get("user_id") == user_id:
                last_read_by_chat[chat_id] = int(member.get("last_read_seq") or 0)

        visible_chats = [chat for chat in chat_rows if chat.id in last_read_by_chat]
        if not visible_chats:
            return [], {}, {}, {}

        user_ids = sorted(
            {
                str(member.get("user_id") or "")
                for chat_id in active_chat_ids
                for member in members_by_chat.get(chat_id, [])
                if member.get("user_id")
            }
        )
        users_by_id, unread_by_chat = self._load_member_users_and_unread_counts(user_id, user_ids, last_read_by_chat)
        return visible_chats, members_by_chat, users_by_id, unread_by_chat

    def _load_member_users_and_unread_counts(
        self,
        user_id: str,
        user_ids: list[str],
        last_read_by_chat: dict[str, int],
    ) -> tuple[dict[str, Any], dict[str, int]]:
        with ThreadPoolExecutor(max_workers=2) as executor:
            users_future = executor.submit(self._users_by_id, user_ids)
            unread_future = executor.submit(self._messages.count_unread_by_chat_ids, user_id, last_read_by_chat)
            return users_future.result(), unread_future.result()

    def _project_chat_entities(self, members: list[dict[str, Any]], users_by_id: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            self._project_known_user_entity(str(member.get("user_id") or ""), users_by_id) for member in members if member.get("user_id")
        ]

    def _chat_title_and_avatar(self, title: str | None, entities: list[dict[str, Any]], viewer_id: str) -> tuple[str, str | None]:
        other_entities = [entity for entity in entities if entity["id"] != viewer_id]
        other_names = [entity["name"] for entity in other_entities if entity.get("name")]
        return title or ", ".join(other_names) or "Chat", other_entities[0]["avatar_url"] if other_entities else None

    def _project_latest_message(self, row: dict[str, Any] | None, users_by_id: dict[str, Any]) -> dict[str, Any] | None:
        if row is None:
            return None
        message = self._normalize_message_row(row)
        sender_id = str(message.get("sender_id") or "")
        sender = users_by_id.get(sender_id)
        if sender is None:
            raise RuntimeError(f"Chat message sender {sender_id} is not a resolvable user row")
        return {
            "content": message.get("content", ""),
            "sender_name": sender.display_name,
            "created_at": message.get("created_at"),
        }

    def _users_by_id(self, user_ids: list[str]) -> dict[str, Any]:
        if not user_ids:
            return {}
        return {user.id: user for user in self._user_repo.list_by_ids(user_ids)}

    def _project_known_user_entity(self, social_user_id: str, users_by_id: dict[str, Any]) -> dict[str, Any]:
        user = users_by_id.get(social_user_id)
        if user is None:
            raise RuntimeError(f"Chat member {social_user_id} is not a resolvable user row")
        return {
            "id": social_user_id,
            "name": user.display_name,
            "type": user.type.value if hasattr(user.type, "value") else str(user.type),
            "avatar_url": avatar_url(user.id, bool(user.avatar)),
        }
