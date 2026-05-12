from __future__ import annotations

import asyncio
from collections.abc import Mapping
from enum import Enum
from typing import Any

from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from backend.threads.chat_adapters.runtime_recipient import select_runtime_notification_recipient
from core.work_item.chat_workflow.service import WorkflowEventChange
from protocols.agent_runtime import (
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
    AgentRuntimeNotificationEnvelope,
    AgentRuntimeTransport,
)


def make_workflow_event_notification_fn(
    app: Any,
    *,
    activity_reader: Any,
    thread_repo: Any,
    user_repo: Any,
    messaging_service: Any,
):
    loop = asyncio.get_running_loop()

    async def notify_runtime(change: WorkflowEventChange) -> None:
        await dispatch_workflow_event_notifications(
            app,
            change=change,
            members=messaging_service.list_chat_members(_required_str(change.event, "chat_id")),
            user_repo=user_repo,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
        )

    def _notify(change: WorkflowEventChange) -> None:
        future = asyncio.run_coroutine_threadsafe(notify_runtime(change), loop)
        future.result()

    return _notify


async def dispatch_workflow_event_notifications(
    app: Any,
    *,
    change: WorkflowEventChange,
    members: list[Mapping[str, Any]],
    user_repo: Any,
    thread_repo: Any,
    activity_reader: Any,
) -> None:
    gateway = get_agent_runtime_gateway(app)
    for envelope in make_workflow_event_notification_envelopes(
        change=change,
        members=members,
        user_repo=user_repo,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
    ):
        await gateway.dispatch_notification(envelope)


def make_workflow_event_notification_envelopes(
    *,
    change: WorkflowEventChange,
    members: list[Mapping[str, Any]],
    user_repo: Any,
    thread_repo: Any,
    activity_reader: Any,
) -> list[AgentRuntimeNotificationEnvelope]:
    sender_user_id = change.actor_user_id
    sender_user = _require_user(user_repo, sender_user_id, "sender")
    sender = AgentRuntimeActor(
        user_id=sender_user_id,
        user_type=_user_type(sender_user, sender_user_id),
        display_name=_display_name(sender_user, sender_user_id),
        source="workflow",
    )
    envelopes: list[AgentRuntimeNotificationEnvelope] = []
    for member in members:
        recipient_user_id = _member_user_id(member)
        if recipient_user_id == sender_user_id:
            continue
        recipient_user = _require_user(user_repo, recipient_user_id, "recipient")
        recipient = select_runtime_notification_recipient(
            recipient_user_id,
            _user_type(recipient_user, recipient_user_id),
            thread_repo=thread_repo,
            activity_reader=activity_reader,
            context="workflow event",
        )
        if recipient is None:
            continue
        envelopes.append(
            make_workflow_event_notification_envelope(
                change=change,
                recipient=recipient,
                sender=sender,
            )
        )
    return envelopes


def make_workflow_event_notification_envelope(
    *,
    change: WorkflowEventChange,
    recipient: AgentChatRecipient,
    sender: AgentRuntimeActor,
) -> AgentRuntimeNotificationEnvelope:
    event = change.event
    chat_id = _required_str(event, "chat_id")
    event_id = _required_str(event, "event_id")
    kind = _required_str(event, "kind")
    state = _required_str(event, "state")
    state_version = _required_int(event, "state_version")
    delivery_key = f"workflow:{chat_id}:{event_id}:{state_version}"
    return AgentRuntimeNotificationEnvelope(
        event_type="chat.workflow.event",
        recipient=recipient,
        sender=sender,
        message=AgentRuntimeMessage(
            content=f"Workflow event {kind} was {change.operation} and is {state}.",
            metadata={
                "chat_id": chat_id,
                "event_id": event_id,
                "kind": kind,
                "operation": change.operation,
                "state": state,
                "state_version": state_version,
            },
        ),
        notification_type="workflow_event",
        transport=AgentRuntimeTransport(
            delivery_id=delivery_key,
            correlation_id=f"workflow:{chat_id}:{event_id}",
            idempotency_key=delivery_key,
        ),
    )


def _required_str(event: Mapping[str, Any], key: str) -> str:
    value = str(event.get(key) or "").strip()
    if not value:
        raise RuntimeError(f"Workflow event notification is missing {key}")
    return value


def _required_int(event: Mapping[str, Any], key: str) -> int:
    value = event.get(key)
    if type(value) is not int:
        raise RuntimeError(f"Workflow event notification has invalid {key}")
    return value


def _member_user_id(member: Mapping[str, Any]) -> str:
    user_id = str(member.get("user_id") or "").strip()
    if not user_id:
        raise RuntimeError("Workflow event notification member row is missing user_id")
    return user_id


def _require_user(user_repo: Any, user_id: str, role: str) -> Any:
    user = user_repo.get_by_id(user_id)
    if user is None:
        raise RuntimeError(f"Workflow event notification {role} user not found: {user_id}")
    return user


def _user_type(user: Any, user_id: str) -> str:
    raw_type = getattr(user, "type", None)
    if raw_type is None:
        raise RuntimeError(f"Workflow event notification user is missing type: {user_id}")
    return raw_type.value if isinstance(raw_type, Enum) else str(raw_type)


def _display_name(user: Any, user_id: str) -> str:
    display_name = getattr(user, "display_name", None)
    if display_name is None:
        raise RuntimeError(f"Workflow event notification user is missing display name: {user_id}")
    return str(display_name)
