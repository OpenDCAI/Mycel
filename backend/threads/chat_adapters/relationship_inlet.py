from __future__ import annotations

import asyncio
from typing import Any

from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from backend.threads.chat_adapters.runtime_identity import display_name, make_runtime_actor, require_user, user_type
from backend.threads.chat_adapters.runtime_recipient import select_runtime_notification_recipient
from messaging.contracts import RelationshipEvent, RelationshipRow
from protocols.agent_runtime import (
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
    AgentRuntimeNotificationEnvelope,
)

_DECISION_VERBS: dict[RelationshipEvent, str] = {
    "approve": "approved",
    "reject": "rejected",
}


def make_relationship_request_notification_fn(app: Any, *, activity_reader: Any, thread_repo: Any, user_repo: Any):
    loop = asyncio.get_running_loop()

    async def notify_runtime(row: RelationshipRow) -> None:
        requester_id = _requester_id(row)
        target_id = _target_id(row, requester_id)
        requester = require_user(user_repo, requester_id, context="Relationship request", role="requester")
        target = require_user(user_repo, target_id, context="Relationship request", role="target")
        target_type = user_type(target, target_id, context="Relationship request")
        recipient = select_runtime_notification_recipient(
            target_id,
            target_type,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
            context="relationship request",
        )
        if recipient is None:
            return
        await _dispatch_notification(
            app,
            recipient=recipient,
            sender=make_runtime_actor(
                user_id=requester_id,
                user=requester,
                source="relationship",
                context="Relationship request",
                include_avatar=True,
            ),
            message=AgentRuntimeMessage(
                content=_notification_content(
                    display_name(requester, requester_id, context="Relationship request"),
                    row.message,
                ),
                metadata={"relationship_id": row.id},
            ),
            event_type="relationship.requested",
        )

    def _notify(row: RelationshipRow) -> None:
        future = asyncio.run_coroutine_threadsafe(notify_runtime(row), loop)
        future.result()

    return _notify


def make_relationship_decision_notification_fn(app: Any, *, activity_reader: Any, thread_repo: Any, user_repo: Any):
    loop = asyncio.get_running_loop()

    async def notify_runtime(row: RelationshipRow, event: RelationshipEvent) -> None:
        requester_id = _requester_id(row)
        decider_id = _target_id(row, requester_id)
        requester = require_user(user_repo, requester_id, context="Relationship request", role="requester")
        decider = require_user(user_repo, decider_id, context="Relationship request", role="decider")
        requester_type = user_type(requester, requester_id, context="Relationship request")
        recipient = select_runtime_notification_recipient(
            requester_id,
            requester_type,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
            context="relationship decision",
        )
        if recipient is None:
            return
        await _dispatch_notification(
            app,
            recipient=recipient,
            sender=make_runtime_actor(
                user_id=decider_id,
                user=decider,
                source="relationship",
                context="Relationship request",
                include_avatar=True,
            ),
            message=AgentRuntimeMessage(
                content=(
                    f"{display_name(decider, decider_id, context='Relationship request')} "
                    f"{_decision_verb(event)} your relationship request."
                ),
                metadata={
                    "relationship_id": row.id,
                    "event": event,
                    "state": row.state,
                },
            ),
            event_type=f"relationship.{_decision_verb(event)}",
        )

    def _notify(row: RelationshipRow, event: RelationshipEvent) -> None:
        future = asyncio.run_coroutine_threadsafe(notify_runtime(row, event), loop)
        future.result()

    return _notify


async def _dispatch_notification(
    app: Any,
    *,
    recipient: AgentChatRecipient,
    sender: AgentRuntimeActor,
    message: AgentRuntimeMessage,
    event_type: str,
) -> None:
    await get_agent_runtime_gateway(app).dispatch_notification(
        AgentRuntimeNotificationEnvelope(
            event_type=event_type,
            recipient=recipient,
            sender=sender,
            message=message,
            notification_type="relationship",
        )
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
