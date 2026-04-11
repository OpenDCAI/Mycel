"""HireVisitDeliveryResolver — delivery action based on relationship state.

Priority chain (highest wins):
1. blocked (contact relation) → DROP
2. HIRE relationship → DELIVER (direct access)
3. @mention override → DELIVER
4. muted contact → NOTIFY
5. muted chat → NOTIFY
6. VISIT relationship → NOTIFY (queue, not direct)
7. stranger (no relationship) → NOTIFY (anti-spam default)
8. Default → DELIVER (same-owner entities, known contacts)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from messaging.delivery.actions import DeliveryAction

logger = logging.getLogger(__name__)


class HireVisitDeliveryResolver:
    """Evaluates delivery action for a chat message recipient.

    Args:
        contact_repo: Provides get(owner, target) → ContactRow-like dict.
        chat_member_repo: Provides list_members(chat_id) → list of member dicts.
        relationship_repo: Provides get(user_a, user_b) → relationship dict.
    """

    def __init__(
        self,
        contact_repo: Any,
        chat_member_repo: Any,
        relationship_repo: Any | None = None,
    ) -> None:
        self._contacts = contact_repo
        self._chat_members = chat_member_repo
        self._relationships = relationship_repo

    def resolve(
        self,
        recipient_id: str,
        chat_id: str,
        sender_id: str,
        *,
        is_mentioned: bool = False,
    ) -> DeliveryAction:
        # 1. Contact-level block — always DROP
        contact = self._get_contact(recipient_id, sender_id)
        if self._is_blocked(contact):
            logger.debug("[resolver] DROP: %s blocked %s", recipient_id[:15], sender_id[:15])
            return DeliveryAction.DROP

        # Fetch relationship once for checks 2, 6, 7
        rel = self._relationships.get(recipient_id, sender_id) if self._relationships else None
        rel_state = rel.get("state") if rel else "none"

        # 2. HIRE → DELIVER
        if rel_state == "hire":
            logger.debug("[resolver] DELIVER: HIRE relationship %s←%s", recipient_id[:15], sender_id[:15])
            return DeliveryAction.DELIVER

        # 3. @mention override — skip mute checks (not block)
        if is_mentioned:
            return DeliveryAction.DELIVER

        # 4. Contact-level mute
        if self._is_muted(contact):
            logger.debug("[resolver] NOTIFY: %s muted %s", recipient_id[:15], sender_id[:15])
            return DeliveryAction.NOTIFY

        # 5. Chat-level mute
        if self._is_chat_muted(recipient_id, chat_id):
            logger.debug("[resolver] NOTIFY: %s muted chat %s", recipient_id[:15], chat_id[:8])
            return DeliveryAction.NOTIFY

        # 6. VISIT → NOTIFY
        if rel_state == "visit":
            logger.debug("[resolver] NOTIFY: VISIT relationship %s←%s", recipient_id[:15], sender_id[:15])
            return DeliveryAction.NOTIFY

        # 7. Stranger (none or no relationship) → NOTIFY (anti-spam)
        if self._relationships and rel_state == "none":
            logger.debug("[resolver] NOTIFY: stranger %s←%s", recipient_id[:15], sender_id[:15])
            return DeliveryAction.NOTIFY

        # 8. Default → DELIVER
        return DeliveryAction.DELIVER

    def _get_contact(self, owner_id: str, target_id: str):
        """Fetch contact row from the directional contacts table."""
        return self._contacts.get(owner_id, target_id)

    def _is_blocked(self, contact: Any | None) -> bool:
        if not contact:
            return False
        if bool(contact.get("blocked")):
            return True
        return contact.get("relation") == "blocked"

    def _is_muted(self, contact: Any | None) -> bool:
        if not contact:
            return False
        if bool(contact.get("muted")):
            return True
        return contact.get("relation") == "muted"

    def _is_chat_muted(self, user_id: str, chat_id: str) -> bool:
        """Check if user has muted this specific chat."""
        members = self._chat_members.list_members(chat_id)

        for member in members:
            if member.get("user_id") != user_id:
                continue
            if not member.get("muted", False):
                return False
            mute_until = member.get("mute_until")
            if mute_until is not None:
                # Handle both timestamp float and ISO string
                if isinstance(mute_until, (int, float)) and mute_until < time.time():
                    return False
            return True
        return False
