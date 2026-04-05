"""Delivery strategy resolver — evaluates per-recipient delivery action.

@@@delivery-strategy-gate — single evaluation point between message storage
and agent delivery. Checks contact-level block/mute → chat-level mute → default.
"""

from __future__ import annotations

import logging
import time

from storage.contracts import ChatEntityRepo, ContactRepo, DeliveryAction

logger = logging.getLogger(__name__)


class DefaultDeliveryResolver:
    """Evaluates delivery action for a chat message recipient.

    Priority (highest wins):
    1. Contact block (sender blocked by recipient) → DROP
    2. Contact mute (sender muted by recipient)   → NOTIFY
    3. Chat mute (recipient muted this chat)       → NOTIFY
    4. Default                                     → DELIVER
    """

    def __init__(self, contact_repo: ContactRepo, chat_entity_repo: ChatEntityRepo) -> None:
        self._contacts = contact_repo
        self._chat_entities = chat_entity_repo

    def resolve(
        self,
        recipient_id: str,
        chat_id: str,
        sender_id: str,
        *,
        is_mentioned: bool = False,
    ) -> DeliveryAction:
        # 1. Contact-level block — always DROP, even if mentioned
        contact = self._contacts.get(recipient_id, sender_id)
        if contact and contact.relation == "blocked":
            logger.debug("[resolver] DROP: %s blocked %s", recipient_id[:15], sender_id[:15])
            return DeliveryAction.DROP

        # @@@mention-override — mentioned entities skip mute checks
        if is_mentioned:
            return DeliveryAction.DELIVER

        # 2. Contact-level mute
        if contact and contact.relation == "muted":
            logger.debug("[resolver] NOTIFY: %s muted %s", recipient_id[:15], sender_id[:15])
            return DeliveryAction.NOTIFY

        # 3. Chat-level mute
        if self._is_chat_muted(recipient_id, chat_id):
            logger.debug("[resolver] NOTIFY: %s muted chat %s", recipient_id[:15], chat_id[:8])
            return DeliveryAction.NOTIFY

        # 4. Default
        return DeliveryAction.DELIVER

    def _is_chat_muted(self, user_id: str, chat_id: str) -> bool:
        """Check if user has muted this specific chat."""
        members = self._chat_entities.list_members(chat_id)
        for ce in members:
            if ce.entity_id == user_id:
                muted = getattr(ce, "muted", False)
                if not muted:
                    return False
                mute_until = getattr(ce, "mute_until", None)
                if mute_until is not None and mute_until < time.time():
                    return False  # mute expired
                return True
        return False
