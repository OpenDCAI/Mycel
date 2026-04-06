"""Chat service — user-to-user communication."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from backend.web.utils.serializers import avatar_url
from storage.contracts import (
    ChatMessageRepo,
    ChatMessageRow,
    ChatParticipantRepo,
    ChatRepo,
    ChatRow,
    DeliveryResolver,
    MemberRepo,
    MemberType,
)

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        chat_repo: ChatRepo,
        chat_participant_repo: ChatParticipantRepo,
        chat_message_repo: ChatMessageRepo,
        member_repo: MemberRepo,
        event_bus: Any = None,
        delivery_fn: Callable | None = None,
        delivery_resolver: DeliveryResolver | None = None,
    ) -> None:
        self._chats = chat_repo
        self._chat_participants = chat_participant_repo
        self._messages = chat_message_repo
        self._members = member_repo
        self._event_bus = event_bus
        self._delivery_fn = delivery_fn
        self._delivery_resolver = delivery_resolver

    def _require_chat(self, chat_id: str) -> ChatRow:
        chat = self._chats.get_by_id(chat_id)
        if chat is None:
            raise RuntimeError(f"Chat {chat_id} not found after creation")
        return chat

    def _resolve_name(self, user_id: str) -> str:
        """Resolve display name from member_repo."""
        m = self._members.get_by_id(user_id) if self._members else None
        return m.name if m else "unknown"

    def find_or_create_chat(self, user_ids: list[str], title: str | None = None) -> ChatRow:
        """Find existing 1:1 chat between two social identities, or create one."""
        if len(user_ids) != 2:
            raise ValueError("Use create_group_chat() for 3+ participants")

        existing_id = self._chat_participants.find_chat_between(user_ids[0], user_ids[1])
        if existing_id:
            return self._require_chat(existing_id)

        now = time.time()
        chat_id = str(uuid.uuid4())
        self._chats.create(ChatRow(id=chat_id, title=title, created_at=now))
        for uid in user_ids:
            self._chat_participants.add_participant(chat_id, uid, now)
        return self._require_chat(chat_id)

    def create_group_chat(self, user_ids: list[str], title: str | None = None) -> ChatRow:
        """Create a group chat with 3+ participants."""
        if len(user_ids) < 3:
            raise ValueError("Group chat requires 3+ participants")
        now = time.time()
        chat_id = str(uuid.uuid4())
        self._chats.create(ChatRow(id=chat_id, title=title, created_at=now))
        for uid in user_ids:
            self._chat_participants.add_participant(chat_id, uid, now)
        return self._require_chat(chat_id)

    def send_message(
        self,
        chat_id: str,
        sender_id: str,
        content: str,
        mentioned_ids: list[str] | None = None,
        signal: str | None = None,
    ) -> ChatMessageRow:
        """Send a message in a chat."""
        logger.debug(
            "[send_message] chat=%s sender=%s content=%.50s signal=%s",
            chat_id[:8],
            sender_id[:15],
            content[:50],
            signal,
        )
        mentions = mentioned_ids or []
        now = time.time()
        msg_id = str(uuid.uuid4())
        msg = ChatMessageRow(
            id=msg_id,
            chat_id=chat_id,
            sender_id=sender_id,
            content=content,
            mentioned_ids=mentions,
            created_at=now,
        )
        self._messages.create(msg)

        sender_name = self._resolve_name(sender_id)

        if self._event_bus:
            self._event_bus.publish(
                chat_id,
                {
                    "event": "message",
                    "data": {
                        "id": msg_id,
                        "chat_id": chat_id,
                        "sender_id": sender_id,
                        "sender_name": sender_name,
                        "content": content,
                        "mentioned_ids": mentions,
                        "created_at": now,
                    },
                },
            )

        self._deliver_to_agents(chat_id, sender_id, sender_name, content, mentions, signal=signal)
        return msg

    def _deliver_to_agents(
        self,
        chat_id: str,
        sender_id: str,
        sender_name: str,
        content: str,
        mentioned_ids: list[str] | None = None,
        signal: str | None = None,
    ) -> None:
        """For each non-sender agent participant in the chat, deliver to their brain thread."""
        mentions = set(mentioned_ids or [])
        participants = self._chat_participants.list_participants(chat_id)
        sender_member = self._members.get_by_id(sender_id) if self._members else None
        sender_avatar_url = avatar_url(sender_id, bool(sender_member.avatar if sender_member else None))

        for ce in participants:
            if ce.user_id == sender_id:
                continue
            member = self._members.get_by_id(ce.user_id) if self._members else None
            if not member or member.type == MemberType.HUMAN or not member.main_thread_id:
                logger.debug(
                    "[deliver] SKIP %s type=%s thread=%s",
                    ce.user_id,
                    getattr(member, "type", None),
                    getattr(member, "main_thread_id", None),
                )
                continue
            if self._delivery_resolver:
                from storage.contracts import DeliveryAction

                is_mentioned = ce.user_id in mentions
                action = self._delivery_resolver.resolve(
                    ce.user_id,
                    chat_id,
                    sender_id,
                    is_mentioned=is_mentioned,
                )
                if action != DeliveryAction.DELIVER:
                    logger.info(
                        "[deliver] POLICY %s for %s (sender=%s chat=%s mentioned=%s)",
                        action.value,
                        ce.user_id,
                        sender_id,
                        chat_id[:8],
                        is_mentioned,
                    )
                    continue
            if self._delivery_fn:
                logger.debug("[deliver] → %s (thread=%s) from=%s", member.id, member.main_thread_id, sender_name)
                try:
                    self._delivery_fn(member, content, sender_name, chat_id, sender_id, sender_avatar_url, signal=signal)
                except Exception:
                    logger.exception("Failed to deliver chat message to member %s", member.id)
            else:
                logger.warning("[deliver] NO delivery_fn for %s", member.id)

    def set_delivery_fn(self, fn) -> None:
        self._delivery_fn = fn

    def list_chats_for_user(self, user_id: str) -> list[dict]:
        """List all chats for a user (social identity) with summary info."""
        chat_ids = self._chat_participants.list_chats_for_user(user_id)
        result = []
        for cid in chat_ids:
            chat = self._chats.get_by_id(cid)
            if not chat or chat.status != "active":
                continue
            participants = self._chat_participants.list_participants(cid)
            entities_info = []
            for p in participants:
                m = self._members.get_by_id(p.user_id) if self._members else None
                if m:
                    entities_info.append(
                        {
                            "id": m.id,
                            "name": m.name,
                            "type": m.type.value if hasattr(m.type, "value") else str(m.type),
                            "avatar_url": avatar_url(m.id, bool(m.avatar)),
                        }
                    )
            msgs = self._messages.list_by_chat(cid, limit=1)
            last_msg = None
            if msgs:
                m = msgs[0]
                last_msg = {
                    "content": m.content,
                    "sender_name": self._resolve_name(m.sender_id),
                    "created_at": m.created_at,
                }
            unread = self._messages.count_unread(cid, user_id)
            has_mention = self._messages.has_unread_mention(cid, user_id)
            result.append(
                {
                    "id": cid,
                    "title": chat.title,
                    "status": chat.status,
                    "created_at": chat.created_at,
                    "entities": entities_info,
                    "last_message": last_msg,
                    "unread_count": unread,
                    "has_mention": has_mention,
                }
            )
        return result
