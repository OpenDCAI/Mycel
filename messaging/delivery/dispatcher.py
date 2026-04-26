"""Agent delivery dispatch for Chat messages."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from messaging.avatars import AvatarUrlBuilder
from messaging.delivery.actions import DeliveryAction
from messaging.delivery.contracts import ChatDeliveryFn, ChatDeliveryRequest
from messaging.delivery.wake_policy import (
    ReceiverWakePreference,
    SenderWakeScope,
    WakeAction,
    WakeSafety,
    compose_wake_action,
)
from messaging.display_user import resolve_messaging_display_user

logger = logging.getLogger(__name__)


class ChatDeliveryDispatcher:
    """Dispatch durable Chat messages to Agent recipients."""

    def __init__(
        self,
        chat_member_repo: Any,
        user_repo: Any,
        *,
        avatar_url_builder: AvatarUrlBuilder | None = None,
        unread_counter: Any | None = None,
        delivery_resolver: Any | None = None,
        delivery_fn: ChatDeliveryFn | None = None,
    ) -> None:
        self._chat_members_repo = chat_member_repo
        self._user_repo = user_repo
        self._avatar_url_builder = avatar_url_builder
        self._unread_counter = unread_counter
        self._delivery_resolver = delivery_resolver
        self._delivery_fn = delivery_fn

    def set_delivery_fn(self, fn: ChatDeliveryFn) -> None:
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
        sender_scope = SenderWakeScope.from_mentions(mentions)
        members = self._chat_members_repo.list_members(chat_id)
        sender_user = self._resolve_display_user(sender_id)
        if sender_user is None:
            raise RuntimeError(f"Chat delivery sender identity not found: {sender_id}")
        sender_name = sender_user.display_name
        sender_avatar_url = self._build_avatar_url(sender_user.id, bool(sender_user.avatar))
        sender_raw_type = getattr(sender_user, "type", None)
        if sender_raw_type is None:
            raise RuntimeError(f"Chat delivery sender type is missing: {sender_id}")
        sender_type = sender_raw_type.value if isinstance(sender_raw_type, Enum) else str(sender_raw_type)
        sender_owner_id = self._runtime_owner_id(sender_user)

        for member in members:
            uid = member.get("user_id")
            if not uid:
                raise RuntimeError(f"Chat delivery member row is missing user_id in chat {chat_id}")
            if uid == sender_id:
                continue
            recipient = self._resolve_display_user(uid)
            if not recipient:
                raise RuntimeError(f"Chat delivery recipient identity not found: {uid}")
            member_raw_type = getattr(recipient, "type", None)
            member_type = member_raw_type.value if isinstance(member_raw_type, Enum) else str(member_raw_type)
            if member_type not in {"agent", "external"}:
                continue

            action = DeliveryAction.DELIVER
            # @@@same-owner-group-delivery - explicit group membership among the same owner
            # is already enough access for runtime delivery; resolver policy is only needed
            # across ownership boundaries.
            if self._needs_access_resolver(sender_owner_id, recipient) and self._delivery_resolver:
                is_mentioned = uid in mention_set
                action = self._delivery_resolver.resolve(uid, chat_id, sender_id, is_mentioned=is_mentioned)

            wake_action = compose_wake_action(
                safety=self._wake_safety(action),
                sender_scope=sender_scope,
                receiver_preference=self._receiver_preference(member, action),
                recipient_is_mentioned=uid in mention_set,
            )
            if wake_action is WakeAction.DROP_RUNTIME:
                logger.info("[messaging] POLICY %s for %s", action.value, uid[:15])
                continue
            if wake_action is WakeAction.NO_WAKE:
                continue

            self._deliver(
                uid,
                recipient,
                content,
                sender_name,
                sender_type,
                chat_id,
                sender_id,
                sender_avatar_url,
                unread_count=self._count_unread(chat_id, uid),
                signal=signal,
            )

    def _resolve_display_user(self, social_user_id: str) -> Any | None:
        return resolve_messaging_display_user(
            user_repo=self._user_repo,
            social_user_id=social_user_id,
        )

    def _count_unread(self, chat_id: str, recipient_id: str) -> int:
        if self._unread_counter is None:
            raise RuntimeError("Chat delivery unread counter is not configured")
        unread_count = self._unread_counter(chat_id, recipient_id)
        if type(unread_count) is not int:
            raise RuntimeError(f"Chat delivery unread count is invalid for {recipient_id}: {unread_count!r}")
        return unread_count

    def _build_avatar_url(self, user_id: str | None, has_avatar: bool) -> str | None:
        if self._avatar_url_builder is None:
            raise RuntimeError("Chat delivery avatar URL builder is not configured")
        return self._avatar_url_builder(user_id, has_avatar)

    def _runtime_owner_id(self, user: Any) -> str | None:
        raw_type = getattr(user, "type", None)
        user_type = raw_type.value if isinstance(raw_type, Enum) else str(raw_type)
        if user_type == "human":
            return getattr(user, "id", None)
        if user_type == "external":
            return getattr(user, "created_by_user_id", None)
        return getattr(user, "owner_user_id", None)

    def _needs_access_resolver(self, sender_owner_id: str | None, recipient: Any) -> bool:
        return not (sender_owner_id and self._runtime_owner_id(recipient) == sender_owner_id)

    def _deliver(
        self,
        recipient_id: str,
        recipient: Any,
        content: str,
        sender_name: str,
        sender_type: str,
        chat_id: str,
        sender_id: str,
        sender_avatar_url: str | None,
        unread_count: int,
        *,
        signal: str | None,
    ) -> None:
        if not self._delivery_fn:
            raise RuntimeError("Chat delivery function is not configured")
        self._delivery_fn(
            ChatDeliveryRequest(
                recipient_id=recipient_id,
                recipient_user=recipient,
                content=content,
                sender_name=sender_name,
                sender_type=sender_type,
                chat_id=chat_id,
                sender_id=sender_id,
                sender_avatar_url=sender_avatar_url,
                unread_count=unread_count,
                signal=signal,
            )
        )

    def _wake_safety(self, action: DeliveryAction) -> WakeSafety:
        if action is DeliveryAction.DROP:
            return WakeSafety.BLOCKED
        return WakeSafety.ALLOWED

    def _receiver_preference(self, member: dict[str, Any], action: DeliveryAction) -> ReceiverWakePreference:
        if bool(member.get("muted", False)) or action is DeliveryAction.NOTIFY:
            return ReceiverWakePreference.QUIET
        return ReceiverWakePreference.DEFAULT
