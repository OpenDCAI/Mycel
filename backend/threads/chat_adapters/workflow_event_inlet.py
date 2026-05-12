from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from backend.threads.chat_adapters.runtime_event_hook import make_sync_runtime_event_hook
from backend.threads.chat_adapters.runtime_notification_action import (
    RuntimeNotificationAction,
    dispatch_runtime_notification_actions,
)
from core.event_actions import plan_event_actions
from core.work_item.chat_workflow.service import WorkflowEventChange
from protocols.agent_runtime import AgentRuntimeTransport


def make_workflow_event_notification_fn(
    app: Any,
    *,
    activity_reader: Any,
    thread_repo: Any,
    user_repo: Any,
    messaging_service: Any,
) -> Callable[[WorkflowEventChange], None]:
    planner = workflow_event_notification_action_planner(messaging_service)

    async def notify_runtime(change: WorkflowEventChange) -> None:
        actions = plan_event_actions([planner], change)
        await dispatch_runtime_notification_actions(
            app,
            actions,
            user_repo=user_repo,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
        )

    return make_sync_runtime_event_hook(notify_runtime)


def workflow_event_notification_action_planner(messaging_service: Any) -> Callable[[WorkflowEventChange], list[RuntimeNotificationAction]]:
    def plan(change: WorkflowEventChange) -> list[RuntimeNotificationAction]:
        return make_workflow_event_notification_actions(
            change,
            messaging_service.list_chat_members(_required_str(change.event, "chat_id")),
        )

    return plan


def make_workflow_event_notification_actions(
    change: WorkflowEventChange,
    members: Sequence[Mapping[str, Any]],
) -> list[RuntimeNotificationAction]:
    actions: list[RuntimeNotificationAction] = []
    for member in members:
        recipient_user_id = _member_user_id(member)
        if recipient_user_id == change.actor_user_id:
            continue
        actions.append(workflow_event_runtime_notification_action(change=change, recipient_user_id=recipient_user_id))
    return actions


def workflow_event_runtime_notification_action(*, change: WorkflowEventChange, recipient_user_id: str) -> RuntimeNotificationAction:
    event = change.event
    chat_id = _required_str(event, "chat_id")
    event_id = _required_str(event, "event_id")
    kind = _required_str(event, "kind")
    state = _required_str(event, "state")
    state_version = _required_int(event, "state_version")
    delivery_key = f"workflow:{chat_id}:{event_id}:{state_version}"
    return RuntimeNotificationAction(
        context="Workflow event notification",
        recipient_user_id=recipient_user_id,
        sender_user_id=change.actor_user_id,
        sender_source="workflow",
        event_type="chat.workflow.event",
        notification_type="workflow_event",
        content=f"Workflow event {kind} was {change.operation} and is {state}.",
        metadata={
            "chat_id": chat_id,
            "event_id": event_id,
            "kind": kind,
            "operation": change.operation,
            "actor_user_id": change.actor_user_id,
            "resource_refs": _resource_refs(event),
            "state": state,
            "state_version": state_version,
        },
        transport=AgentRuntimeTransport(
            delivery_id=delivery_key,
            correlation_id=f"workflow:{chat_id}:{event_id}",
            idempotency_key=delivery_key,
        ),
        runtime_context="workflow event",
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


def _resource_refs(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(ref) for ref in event.get("resource_refs") or []]


def _member_user_id(member: Mapping[str, Any]) -> str:
    user_id = str(member.get("user_id") or "").strip()
    if not user_id:
        raise RuntimeError("Workflow event notification member row is missing user_id")
    return user_id
