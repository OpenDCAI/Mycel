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
from typing import Any

from backend.web.utils.serializers import avatar_url
from messaging.contracts import ContentType, MessageType
from messaging.display_user import resolve_messaging_display_user

logger = logging.getLogger(__name__)


class MessagingService:
    """Core messaging operations backed by Supabase repos."""

    def __init__(
        self,
        chat_repo: Any,  # storage.providers.sqlite.chat_repo.SQLiteChatRepo (for chat creation)
        chat_member_repo: Any,  # SupabaseChatMemberRepo or compatible
        messages_repo: Any,  # SupabaseMessagesRepo
        message_read_repo: Any,  # SupabaseMessageReadRepo
        user_repo: Any,  # UserRepo (for name + avatar lookup)
        thread_repo: Any | None = None,  # ThreadRepo for thread-user-id -> agent-user display lookup
        delivery_resolver: Any | None = None,
        delivery_fn: Callable | None = None,
        event_bus: Any | None = None,  # ChatEventBus or SupabaseRealtimeBridge (optional)
    ) -> None:
        self._chats = chat_repo
        self._members_repo = chat_member_repo
        self._messages = messages_repo
        self._user_repo = user_repo
        self._thread_repo = thread_repo
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

    def _resolve_display_user(self, social_user_id: str) -> Any | None:
        return resolve_messaging_display_user(
            user_repo=self._user_repo,
            thread_repo=self._thread_repo,
            social_user_id=social_user_id,
        )

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
        sender = self._resolve_display_user(sender_id)
        sender_name = sender.display_name if sender else "unknown"
        if self._event_bus:
            self._event_bus.publish(
                chat_id,
                {
                    "event": "message",
                    "data": {**created, "sender_name": sender_name},
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
        sender_type = (
            sender_user.type.value
            if hasattr(sender_user, "type") and hasattr(sender_user.type, "value")
            else getattr(sender_user, "type", None)
        )
        sender_owner_id = sender_user.id if sender_type == "human" else getattr(sender_user, "owner_user_id", None)

        for member in members:
            uid = member.get("user_id")
            if not uid or uid == sender_id:
                continue
            m = self._resolve_display_user(uid)
            member_type = m.type.value if hasattr(getattr(m, "type", None), "value") else getattr(m, "type", None)
            if not m or member_type == "human":
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

    def list_unread(self, chat_id: str, user_id: str) -> list[dict[str, Any]]:
        return [self._normalize_message_row(row) for row in self._messages.list_unread(chat_id, user_id)]

    def count_unread(self, chat_id: str, user_id: str) -> int:
        return self._messages.count_unread(chat_id, user_id)

    def search_messages(self, query: str, *, chat_id: str | None = None) -> list[dict[str, Any]]:
        return self._messages.search(query, chat_id=chat_id)

    def list_chat_members(self, chat_id: str) -> list[dict[str, Any]]:
        return self._members_repo.list_members(chat_id)

    def is_chat_member(self, chat_id: str, user_id: str) -> bool:
        return self._members_repo.is_member(chat_id, user_id)

    def update_mute(self, chat_id: str, user_id: str, muted: bool, mute_until: str | None) -> None:
        self._members_repo.update_mute(chat_id, user_id, muted, mute_until)

    def list_chats_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """List all active chats for user with summary info."""
        chat_ids = self._members_repo.list_chats_for_user(user_id)
        result = []
        for cid in chat_ids:
            chat = self._chats.get_by_id(cid)
            if not chat or chat.status != "active":
                continue
            members = self._members_repo.list_members(cid)
            entities_info = []
            for m in members:
                uid = m.get("user_id")
                e = self._resolve_display_user(uid) if uid else None
                if e:
                    entities_info.append(
                        {
                            "id": uid,
                            "name": e.display_name,
                            "type": e.type,
                            "avatar_url": avatar_url(e.id, bool(e.avatar)),
                        }
                    )
            msgs = self._messages.list_by_chat(cid, limit=1)
            last_msg = None
            if msgs:
                m = self._normalize_message_row(msgs[-1])
                sender = self._resolve_display_user(m.get("sender_id", ""))
                last_msg = {
                    "content": m.get("content", ""),
                    "sender_name": sender.display_name if sender else "unknown",
                    "created_at": m.get("created_at"),
                }
            unread = self.count_unread(cid, user_id)
            result.append(
                {
                    "id": cid,
                    "title": chat.title,
                    "status": chat.status,
                    "created_at": chat.created_at,
                    "entities": entities_info,
                    "last_message": last_msg,
                    "unread_count": unread,
                    "has_mention": False,  # TODO: implement mention tracking
                }
            )
        return result
