"""RelationshipService — Hire/Visit lifecycle management."""

from __future__ import annotations

import logging
from typing import Any

from messaging._utils import now_iso
from messaging.contracts import RelationshipEvent, RelationshipRow, RelationshipState
from messaging.relationships.state_machine import transition

logger = logging.getLogger(__name__)


class RelationshipService:
    """Manages Hire/Visit relationships between users."""

    def __init__(self, relationship_repo: Any, member_repo: Any = None, thread_repo: Any = None) -> None:
        self._repo = relationship_repo
        self._member_repo = member_repo
        self._thread_repo = thread_repo

    def _resolve_display_member(self, social_user_id: str) -> Any | None:
        member = self._member_repo.get_by_id(social_user_id) if self._member_repo is not None else None
        if member is not None:
            return member
        if self._thread_repo is None or self._member_repo is None:
            return None
        thread = self._thread_repo.get_by_user_id(social_user_id)
        if thread is None:
            return None
        member_id = thread.get("member_id")
        if not member_id:
            return None
        return self._member_repo.get_by_id(member_id)

    def apply_event(
        self,
        actor_id: str,
        target_id: str,
        event: RelationshipEvent,
        *,
        hire_snapshot: dict[str, Any] | None = None,
    ) -> RelationshipRow:
        """Apply an event to the relationship between actor and target.

        Returns the updated RelationshipRow.
        Raises TransitionError on invalid transition.
        """
        # Ensure canonical ordering
        if actor_id < target_id:
            pa, pb = actor_id, target_id
            requester_is_a = True
        else:
            pa, pb = target_id, actor_id
            requester_is_a = False

        existing = self._repo.get(actor_id, target_id)
        if existing is None:
            current_state: RelationshipState = "none"
            current_direction = None
        else:
            current_state = existing["state"]
            current_direction = existing.get("direction")

        new_state, new_direction = transition(current_state, current_direction, event, requester_is_a=requester_is_a)
        logger.info(
            "[relationship] %s + %s → %s (actor=%s event=%s)",
            current_state,
            event,
            new_state,
            actor_id[:15],
            event,
        )

        fields: dict[str, Any] = {"state": new_state, "direction": new_direction}
        if new_state == "hire" and current_state != "hire":
            fields["hire_granted_at"] = now_iso()
            if hire_snapshot:
                fields["hire_snapshot"] = hire_snapshot
        if new_state == "none" and current_state in ("hire", "visit"):
            fields["hire_revoked_at"] = now_iso()
            if current_state == "hire" and self._member_repo is not None:
                other_id = pb if actor_id == pa else pa
                # @@@thread-user-hire-snapshot - relationship principals can now be thread-owned
                # social user_ids, so the snapshot name must resolve back through thread -> member.
                m = self._resolve_display_member(other_id)
                fields["hire_snapshot"] = {
                    "user_id": other_id,
                    "name": m.name if m else other_id,
                    "snapshot_at": now_iso(),
                }

        row = self._repo.upsert(actor_id, target_id, **fields)
        return RelationshipRow.model_validate(row)

    def request(self, requester_id: str, target_id: str) -> RelationshipRow:
        return self.apply_event(requester_id, target_id, "request")

    def approve(self, approver_id: str, requester_id: str) -> RelationshipRow:
        return self.apply_event(approver_id, requester_id, "approve")

    def reject(self, approver_id: str, requester_id: str) -> RelationshipRow:
        return self.apply_event(approver_id, requester_id, "reject")

    def upgrade(self, owner_id: str, agent_id: str, snapshot: dict[str, Any] | None = None) -> RelationshipRow:
        return self.apply_event(owner_id, agent_id, "upgrade", hire_snapshot=snapshot)

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
