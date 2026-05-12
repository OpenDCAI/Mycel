from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from backend.threads.chat_adapters.runtime_identity import display_name, require_user
from backend.threads.chat_adapters.runtime_notification_action import (
    RuntimeNotificationAction,
    make_runtime_notification_event_hook,
)
from core.event_actions import single_event_action_planner
from messaging.contracts import RelationshipEvent, RelationshipRow

_DECISION_VERBS: dict[RelationshipEvent, str] = {
    "approve": "approved",
    "reject": "rejected",
}


@dataclass(frozen=True)
class RelationshipDecisionChange:
    row: RelationshipRow
    event: RelationshipEvent


def make_relationship_request_notification_fn(app: Any, *, activity_reader: Any, thread_repo: Any, user_repo: Any):
    planner = relationship_request_notification_action_planner(user_repo)
    return make_runtime_notification_event_hook(
        app,
        planner,
        user_repo=user_repo,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
    )


def relationship_request_notification_action_planner(user_repo: Any) -> Callable[[RelationshipRow], list[RuntimeNotificationAction]]:
    def make_action(row: RelationshipRow) -> RuntimeNotificationAction:
        return relationship_request_notification_action(row, user_repo=user_repo)

    return single_event_action_planner(make_action)


def relationship_request_notification_action(row: RelationshipRow, *, user_repo: Any) -> RuntimeNotificationAction:
    requester_id = _requester_id(row)
    target_id = _target_id(row, requester_id)
    requester = require_user(user_repo, requester_id, context="Relationship request", role="requester")
    return RuntimeNotificationAction(
        context="Relationship request",
        recipient_user_id=target_id,
        sender_user_id=requester_id,
        sender_source="relationship",
        event_type="relationship.requested",
        notification_type="relationship",
        content=_notification_content(
            display_name(requester, requester_id, context="Relationship request"),
            row.message,
        ),
        metadata={"relationship_id": row.id},
        include_sender_avatar=True,
    )


def make_relationship_decision_notification_fn(app: Any, *, activity_reader: Any, thread_repo: Any, user_repo: Any):
    planner = relationship_decision_notification_action_planner(user_repo)
    planned_hook = make_runtime_notification_event_hook(
        app,
        planner,
        user_repo=user_repo,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
    )

    def notify_runtime(row: RelationshipRow, event: RelationshipEvent) -> None:
        planned_hook(RelationshipDecisionChange(row=row, event=event))

    return notify_runtime


def relationship_decision_notification_action_planner(
    user_repo: Any,
) -> Callable[[RelationshipDecisionChange], list[RuntimeNotificationAction]]:
    def make_action(change: RelationshipDecisionChange) -> RuntimeNotificationAction:
        return relationship_decision_notification_action(change, user_repo=user_repo)

    return single_event_action_planner(make_action)


def relationship_decision_notification_action(change: RelationshipDecisionChange, *, user_repo: Any) -> RuntimeNotificationAction:
    row = change.row
    event = change.event
    requester_id = _requester_id(row)
    decider_id = _target_id(row, requester_id)
    verb = _decision_verb(event)
    decider = require_user(user_repo, decider_id, context="Relationship request", role="decider")
    return RuntimeNotificationAction(
        context="Relationship request",
        recipient_user_id=requester_id,
        sender_user_id=decider_id,
        sender_source="relationship",
        event_type=f"relationship.{verb}",
        notification_type="relationship",
        content=f"{display_name(decider, decider_id, context='Relationship request')} {verb} your relationship request.",
        metadata={
            "relationship_id": row.id,
            "event": event,
            "state": row.state,
        },
        include_sender_avatar=True,
    )


def _requester_id(row: RelationshipRow) -> str:
    if row.initiator_user_id is None:
        raise RuntimeError(f"Relationship request row is missing initiator: {row.id}")
    return row.initiator_user_id


def _target_id(row: RelationshipRow, requester_id: str) -> str:
    if requester_id == row.user_low:
        return row.user_high
    if requester_id == row.user_high:
        return row.user_low
    raise RuntimeError(f"Relationship request initiator is not a party: {row.id}")


def _notification_content(requester_name: str, message: str | None) -> str:
    base = f"{requester_name} requested a relationship with you."
    if message and message.strip():
        base = f"{base} Message: {message.strip()}"
    return f"{base} Review the pending relationship request in Mycel, then approve or reject it."


def _decision_verb(event: RelationshipEvent) -> str:
    try:
        return _DECISION_VERBS[event]
    except KeyError as exc:
        raise RuntimeError(f"Relationship decision notification does not support event: {event}") from exc
