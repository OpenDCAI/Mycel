"""Hire/Visit relationship state machine — pure functions, no I/O.

State transitions:
  NONE             + request   → PENDING (direction set)
  PENDING_A_TO_B   + approve   → VISIT
  PENDING_A_TO_B   + reject    → NONE
  PENDING_B_TO_A   + approve   → VISIT
  PENDING_B_TO_A   + reject    → NONE
  VISIT            + upgrade   → HIRE
  HIRE             + downgrade → VISIT
  HIRE | VISIT     + revoke    → NONE
"""

from __future__ import annotations

from messaging.contracts import (
    RelationshipDirection,
    RelationshipEvent,
    RelationshipState,
)


class TransitionError(ValueError):
    """Invalid state machine transition."""


def transition(
    current_state: RelationshipState,
    current_direction: RelationshipDirection | None,
    event: RelationshipEvent,
    *,
    requester_is_a: bool,
) -> tuple[RelationshipState, RelationshipDirection | None]:
    """Apply an event and return (new_state, new_direction).

    Args:
        current_state: The current relationship state.
        current_direction: Current direction (only relevant for pending states).
        event: The event to apply.
        requester_is_a: True if the actor is principal_a (lexicographically smaller id).

    Returns:
        (new_state, new_direction)

    Raises:
        TransitionError: If the transition is not valid in the current state.
    """
    match (current_state, event):
        case ("none", "request"):
            direction: RelationshipDirection = "a_to_b" if requester_is_a else "b_to_a"
            return ("pending_a_to_b" if requester_is_a else "pending_b_to_a", direction)

        case ("pending_a_to_b", "approve") if not requester_is_a:
            # b approves a's request
            return ("visit", None)

        case ("pending_b_to_a", "approve") if requester_is_a:
            # a approves b's request
            return ("visit", None)

        case ("pending_a_to_b", "reject") if not requester_is_a:
            return ("none", None)

        case ("pending_b_to_a", "reject") if requester_is_a:
            return ("none", None)

        # Requester can cancel their own pending request
        case ("pending_a_to_b", "revoke") if requester_is_a:
            return ("none", None)

        case ("pending_b_to_a", "revoke") if not requester_is_a:
            return ("none", None)

        case (("visit" | "hire"), "revoke"):
            return ("none", None)

        case ("visit", "upgrade"):
            return ("hire", None)

        case ("hire", "downgrade"):
            return ("visit", None)

        case _:
            raise TransitionError(
                f"Invalid transition: state={current_state!r} event={event!r} requester_is_a={requester_is_a}"
            )


def resolve_direction(
    relationship: dict,
    actor_id: str,
) -> bool:
    """Return True if actor_id is principal_a (used to compute requester_is_a)."""
    return actor_id == relationship.get("principal_a")


def get_pending_direction(state: RelationshipState, principal_a: str, principal_b: str) -> tuple[str, str] | None:
    """Return (requester_id, approver_id) for a pending state, or None."""
    if state == "pending_a_to_b":
        return (principal_a, principal_b)
    if state == "pending_b_to_a":
        return (principal_b, principal_a)
    return None
