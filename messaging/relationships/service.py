"""RelationshipService — Hire/Visit lifecycle management."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from messaging.contracts import RelationshipEvent, RelationshipRow, RelationshipState
from messaging.relationships.state_machine import transition

logger = logging.getLogger(__name__)


class RelationshipService:
    """Manages Hire/Visit relationships between users."""

    def __init__(
        self,
        relationship_repo: Any,
        *,
        on_relationship_requested: Callable[[RelationshipRow], None] | None = None,
    ) -> None:
        self._repo = relationship_repo
        self._on_relationship_requested = on_relationship_requested

    def set_relationship_request_notification_fn(self, fn: Callable[[RelationshipRow], None]) -> None:
        self._on_relationship_requested = fn

    def apply_event(
        self,
        requester_id: str,
        target_id: str,
        event: RelationshipEvent,
    ) -> RelationshipRow:
        """Apply an event to the relationship between requester and target.

        Returns the updated RelationshipRow.
        Raises TransitionError on invalid transition.
        """
        user_low, user_high = sorted((requester_id, target_id))

        existing = self._repo.get(requester_id, target_id)
        if existing is None:
            current_state: RelationshipState = "none"
            initiator_user_id = requester_id if event == "request" else None
        else:
            current_state = existing["state"]
            initiator_user_id = existing.get("initiator_user_id")

        new_state = transition(
            current_state,
            event,
            requester_is_initiator=initiator_user_id is not None and requester_id == initiator_user_id,
        )
        logger.info(
            "[relationship] %s + %s → %s (requester=%s event=%s)",
            current_state,
            event,
            new_state,
            requester_id[:15],
            event,
        )

        row = self._repo.upsert(requester_id, target_id, state=new_state, initiator_user_id=initiator_user_id)
        return RelationshipRow.model_validate(row)

    def request(self, requester_id: str, target_id: str) -> RelationshipRow:
        row = self.apply_event(requester_id, target_id, "request")
        if self._on_relationship_requested is not None:
            self._on_relationship_requested(row)
        return row

    def approve(self, approver_id: str, requester_id: str) -> RelationshipRow:
        return self.apply_event(approver_id, requester_id, "approve")

    def reject(self, approver_id: str, requester_id: str) -> RelationshipRow:
        return self.apply_event(approver_id, requester_id, "reject")

    def upgrade(self, owner_id: str, agent_id: str) -> RelationshipRow:
        return self.apply_event(owner_id, agent_id, "upgrade")

    def downgrade(self, owner_id: str, agent_id: str) -> RelationshipRow:
        return self.apply_event(owner_id, agent_id, "downgrade")

    def revoke(self, revoker_id: str, other_id: str) -> RelationshipRow:
        return self.apply_event(revoker_id, other_id, "revoke")

    def list_for_user(self, user_id: str) -> list[RelationshipRow]:
        rows = self._repo.list_for_user(user_id)
        result = []
        for r in rows:
            try:
                result.append(RelationshipRow.model_validate(r))
            except Exception as exc:
                raise RuntimeError(f"Invalid relationship row {r.get('id') or '<missing>'}") from exc
        return result

    def get_by_id(self, relationship_id: str) -> dict | None:
        return self._repo.get_by_id(relationship_id)

    def get_state(self, user_a: str, user_b: str) -> RelationshipState:
        existing = self._repo.get(user_a, user_b)
        if not existing:
            return "none"
        try:
            if "state" not in existing:
                raise ValueError("missing relationship state")
            return RelationshipRow.model_validate(existing).state
        except Exception as exc:
            raise RuntimeError(f"Invalid relationship row {existing.get('id') or '<missing>'}") from exc
