"""MessagingService — core business logic for the messaging module.

Wraps Supabase messaging repos with business rules:
- create_chat, find_or_create_chat
- send (with delivery routing)
- retract, delete_for, mark_read
- list_messages, list_chats
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from backend.web.utils.serializers import avatar_url
from messaging._utils import now_iso
from messaging.contracts import ContentType, MessageType

logger = logging.getLogger(__name__)


class MessagingService:
    """Core messaging operations backed by Supabase repos."""

    def __init__(
        self,
        chat_repo: Any,  # storage.providers.sqlite.chat_repo.SQLiteChatRepo (for chat creation)
        chat_member_repo: Any,  # SupabaseChatMemberRepo or compatible
        messages_repo: Any,  # SupabaseMessagesRepo
        message_read_repo: Any,  # SupabaseMessageReadRepo
        member_repo: Any,  # MemberRepo (for name + avatar lookup)
        delivery_resolver: Any | None = None,
        delivery_fn: Callable | None = None,
        event_bus: Any | None = None,  # ChatEventBus or SupabaseRealtimeBridge (optional)
    ) -> None:
        self._chats = chat_repo
        self._members_repo = chat_member_repo
        self._messages = messages_repo
        self._reads = message_read_repo
        self._member_repo = member_repo
        self._delivery_resolver = delivery_resolver
        self._delivery_fn = delivery_fn
        self._event_bus = event_bus

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
        import time

        from storage.contracts import ChatRow

        chat_id = str(uuid.uuid4())
        now = time.time()
        self._chats.create(ChatRow(id=chat_id, title=title, status="active", created_at=now))
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
    ) -> dict[str, Any]:
        msg_id = str(uuid.uuid4())

        row: dict[str, Any] = {
            "id": msg_id,
            "chat_id": chat_id,
            "sender_id": sender_id,
            "content": content,
            "content_type": content_type,
            "message_type": message_type,
            "mentions": mentions or [],
            "created_at": now_iso(),
        }
        if signal in ("open", "yield", "close"):
            row["signal"] = signal
        if reply_to:
            row["reply_to"] = reply_to
        if ai_metadata:
            row["ai_metadata"] = ai_metadata

        created = self._messages.create(row)
        logger.debug("[messaging] send chat=%s sender=%s msg=%s type=%s", chat_id[:8], sender_id[:15], msg_id[:8], message_type)

        # Publish to event bus (SSE / Realtime bridge)
        sender = self._member_repo.get_by_id(sender_id)
        sender_name = sender.name if sender else "unknown"
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
        sender_member = self._member_repo.get_by_id(sender_id)
        sender_name = sender_member.name if sender_member else "unknown"
        sender_avatar_url = avatar_url(sender_id, bool(sender_member.avatar if sender_member else None))

        for member in members:
            uid = member.get("user_id")
            if not uid or uid == sender_id:
                continue
            m = self._member_repo.get_by_id(uid)
            if not m or m.type == "human" or not m.main_thread_id:
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
                    self._delivery_fn(m, content, sender_name, chat_id, sender_id, sender_avatar_url, signal=signal)
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
        self._members_repo.update_last_read(chat_id, user_id)
        # Also write per-message reads for recent messages
        msgs = self._messages.list_by_chat(chat_id, limit=50, viewer_id=user_id)
        msg_ids = [m["id"] for m in msgs if m.get("sender_id") != user_id]
        if msg_ids:
            self._reads.mark_chat_read(chat_id, user_id, msg_ids)

    def mark_message_read(self, message_id: str, user_id: str) -> None:
        self._reads.mark_read(message_id, user_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_messages(
        self, chat_id: str, *, limit: int = 50, before: str | None = None, viewer_id: str | None = None
    ) -> list[dict[str, Any]]:
        return self._messages.list_by_chat(chat_id, limit=limit, before=before, viewer_id=viewer_id)

    def list_unread(self, chat_id: str, user_id: str) -> list[dict[str, Any]]:
        return self._messages.list_unread(chat_id, user_id)

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
                e = self._member_repo.get_by_id(uid) if uid else None
                if e:
                    entities_info.append(
                        {
                            "id": e.id,
                            "name": e.name,
                            "type": e.type,
                            "avatar_url": avatar_url(e.id, bool(e.avatar)),
                        }
                    )
            msgs = self._messages.list_by_chat(cid, limit=1)
            last_msg = None
            if msgs:
                m = msgs[-1]
                sender = self._member_repo.get_by_id(m.get("sender_id", ""))
                last_msg = {
                    "content": m.get("content", ""),
                    "sender_name": sender.name if sender else "unknown",
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
