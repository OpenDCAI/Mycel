"""RelationshipService — Hire/Visit lifecycle management."""

from __future__ import annotations

import logging
from typing import Any

from messaging.contracts import RelationshipEvent, RelationshipRow, RelationshipState
from messaging.relationships.state_machine import transition

logger = logging.getLogger(__name__)


class RelationshipService:
    """Manages Hire/Visit relationships between users."""

    def __init__(self, relationship_repo: Any) -> None:
        self._repo = relationship_repo

    def apply_event(
        self,
        actor_id: str,
        target_id: str,
        event: RelationshipEvent,
    ) -> RelationshipRow:
        """Apply an event to the relationship between actor and target.

        Returns the updated RelationshipRow.
        Raises TransitionError on invalid transition.
        """
        user_low, user_high = sorted((actor_id, target_id))

        existing = self._repo.get(actor_id, target_id)
        if existing is None:
            current_state: RelationshipState = "none"
            initiator_user_id = actor_id if event == "request" else None
        else:
            current_state = existing["state"]
            initiator_user_id = existing.get("initiator_user_id")

        new_state = transition(
            current_state,
            event,
            actor_is_initiator=initiator_user_id is not None and actor_id == initiator_user_id,
        )
        logger.info(
            "[relationship] %s + %s → %s (actor=%s event=%s)",
            current_state,
            event,
            new_state,
            actor_id[:15],
            event,
        )

        row = self._repo.upsert(actor_id, target_id, state=new_state, initiator_user_id=initiator_user_id)
        return RelationshipRow.model_validate(row)

    def request(self, requester_id: str, target_id: str) -> RelationshipRow:
        return self.apply_event(requester_id, target_id, "request")

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
            except Exception:
                logger.warning("[relationship] invalid row: %s", r)
        return result

    def get_by_id(self, relationship_id: str) -> dict | None:
        return self._repo.get_by_id(relationship_id)

    def get_state(self, user_a: str, user_b: str) -> RelationshipState:
        existing = self._repo.get(user_a, user_b)
        if not existing:
            return "none"
        return existing.get("state", "none")
