"""HireVisitDeliveryResolver — receiver access and quiet policy.

Priority chain (highest wins):
1. blocked contact → DROP
2. muted contact → NOTIFY
3. muted chat → NOTIFY
4. otherwise → DELIVER
"""

from __future__ import annotations

import logging
import time
from typing import Any

from messaging.contracts import RelationshipRow
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
        contact = self._get_contact(recipient_id, sender_id)
        if self._is_blocked(contact):
            logger.debug("[resolver] DROP: %s blocked %s", recipient_id[:15], sender_id[:15])
            return DeliveryAction.DROP

        rel = self._relationships.get(recipient_id, sender_id) if self._relationships else None
        if rel:
            self._relationship_state(rel)

        if self._is_muted(contact):
            logger.debug("[resolver] NOTIFY: %s muted %s", recipient_id[:15], sender_id[:15])
            return DeliveryAction.NOTIFY

        if self._is_chat_muted(recipient_id, chat_id):
            logger.debug("[resolver] NOTIFY: %s muted chat %s", recipient_id[:15], chat_id[:8])
            return DeliveryAction.NOTIFY

        return DeliveryAction.DELIVER

    def _relationship_state(self, relationship: dict[str, Any]) -> str:
        try:
            if "state" not in relationship:
                raise ValueError("missing relationship state")
            return RelationshipRow.model_validate(relationship).state
        except Exception as exc:
            raise RuntimeError(f"Invalid relationship row {relationship.get('id') or '<missing>'}") from exc

    def _get_contact(self, owner_id: str, target_id: str):
        """Fetch contact row from the directional contacts table."""
        return self._contacts.get(owner_id, target_id)

    def _is_blocked(self, contact: Any | None) -> bool:
        if not contact:
            return False
        if bool(self._contact_value(contact, "blocked")):
            return True
        return self._contact_value(contact, "relation") == "blocked" or self._contact_value(contact, "kind") == "blocked"

    def _is_muted(self, contact: Any | None) -> bool:
        if not contact:
            return False
        if bool(self._contact_value(contact, "muted")):
            return True
        return self._contact_value(contact, "relation") == "muted" or self._contact_value(contact, "kind") == "muted"

    def _contact_value(self, contact: Any, key: str) -> Any:
        if isinstance(contact, dict):
            return contact.get(key)
        return getattr(contact, key, None)

    def _is_chat_muted(self, user_id: str, chat_id: str) -> bool:
        """Check if user has muted this specific chat."""
        members = self._chat_members.list_members(chat_id)

        for member in members:
            member_user_id = member.get("user_id")
            if not member_user_id:
                raise RuntimeError(f"Chat mute member row is missing user_id in chat {chat_id}")
            if member_user_id != user_id:
                continue
            if not member.get("muted", False):
                return False
            mute_until = member.get("mute_until")
            if mute_until is not None:
                # Handle both timestamp float and ISO string
                if isinstance(mute_until, (int, float)) and mute_until < time.time():
                    return False
            return True
        raise RuntimeError(f"Chat {chat_id} is missing delivery recipient member row {user_id}")
