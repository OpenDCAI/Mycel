"""Agent delivery dispatch for Chat messages."""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum
from typing import Any

from backend.web.utils.serializers import avatar_url
from messaging.delivery.actions import DeliveryAction
from messaging.display_user import resolve_messaging_display_user

logger = logging.getLogger(__name__)


class ChatDeliveryDispatcher:
    """Dispatch durable Chat messages to Agent recipients."""

    def __init__(
        self,
        chat_member_repo: Any,
        user_repo: Any,
        delivery_resolver: Any | None = None,
        delivery_fn: Callable | None = None,
    ) -> None:
        self._chat_members_repo = chat_member_repo
        self._user_repo = user_repo
        self._delivery_resolver = delivery_resolver
        self._delivery_fn = delivery_fn

    def set_delivery_fn(self, fn: Callable) -> None:
        self._delivery_fn = fn

    def dispatch(
        self,
        chat_id: str,
        sender_id: str,
        content: str,
        mentions: list[str],
        signal: str | None = None,
    ) -> None:
        mention_set = set(mentions)
        members = self._chat_members_repo.list_members(chat_id)
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
            recipient = self._resolve_display_user(uid)
            if not recipient:
                continue
            member_raw_type = getattr(recipient, "type", None)
            member_type = member_raw_type.value if isinstance(member_raw_type, Enum) else member_raw_type
            if member_type == "human":
                continue

            # @@@same-owner-group-delivery - explicit group membership among the same owner
            # must reach sibling actors even when no relationship row exists yet.
            if sender_owner_id and getattr(recipient, "owner_user_id", None) == sender_owner_id:
                self._deliver(uid, recipient, content, sender_name, chat_id, sender_id, sender_avatar_url, signal=signal)
                continue

            if self._delivery_resolver:
                is_mentioned = uid in mention_set
                action = self._delivery_resolver.resolve(uid, chat_id, sender_id, is_mentioned=is_mentioned)
                if action != DeliveryAction.DELIVER:
                    logger.info("[messaging] POLICY %s for %s", action.value, uid[:15])
                    continue

            self._deliver(uid, recipient, content, sender_name, chat_id, sender_id, sender_avatar_url, signal=signal)

    def _resolve_display_user(self, social_user_id: str) -> Any | None:
        return resolve_messaging_display_user(
            user_repo=self._user_repo,
            social_user_id=social_user_id,
        )

    def _deliver(
        self,
        recipient_id: str,
        recipient: Any,
        content: str,
        sender_name: str,
        chat_id: str,
        sender_id: str,
        sender_avatar_url: str | None,
        *,
        signal: str | None,
    ) -> None:
        if not self._delivery_fn:
            return
        try:
            self._delivery_fn(recipient_id, recipient, content, sender_name, chat_id, sender_id, sender_avatar_url, signal=signal)
        except Exception:
            logger.exception("[messaging] delivery failed for member %s", recipient_id)
