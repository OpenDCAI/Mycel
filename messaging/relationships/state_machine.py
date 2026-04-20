"""Hire/Visit relationship state machine — pure functions, no I/O.

State transitions:
  NONE    + request   → PENDING
  PENDING + approve   → VISIT
  PENDING + reject    → NONE
  PENDING + revoke    → NONE
  VISIT   + upgrade   → HIRE
  HIRE    + downgrade → VISIT
  HIRE | VISIT + revoke → NONE
"""

from __future__ import annotations

from messaging.contracts import RelationshipEvent, RelationshipState


class TransitionError(ValueError):
    """Invalid state machine transition."""


def transition(
    current_state: RelationshipState,
    event: RelationshipEvent,
    *,
    actor_is_initiator: bool,
) -> RelationshipState:
    """Apply an event and return the new state.

    Args:
        current_state: The current relationship state.
        event: The event to apply.
        actor_is_initiator: True if the actor originally created the pending request.

    Returns:
        new_state

    Raises:
        TransitionError: If the transition is not valid in the current state.
    """
    match (current_state, event):
        case ("none", "request"):
            return "pending"

        case ("pending", "approve") if not actor_is_initiator:
            return "visit"

        case ("pending", "reject") if not actor_is_initiator:
            return "none"

        # Requester can cancel their own pending request
        case ("pending", "revoke") if actor_is_initiator:
            return "none"

        case (("visit" | "hire"), "revoke"):
            return "none"

        case ("visit", "upgrade"):
            return "hire"

        case ("hire", "downgrade"):
            return "visit"

        case _:
            raise TransitionError(f"Invalid transition: state={current_state!r} event={event!r} actor_is_initiator={actor_is_initiator}")
