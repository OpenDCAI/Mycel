from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from protocols.agent_runtime import (
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
    AgentRuntimeNotificationEnvelope,
    AgentRuntimeTransport,
)


async def dispatch_workflow_event_notification(
    app: Any,
    *,
    event: Mapping[str, Any],
    recipient: AgentChatRecipient,
    sender: AgentRuntimeActor,
) -> None:
    await get_agent_runtime_gateway(app).dispatch_notification(
        make_workflow_event_notification_envelope(
            event=event,
            recipient=recipient,
            sender=sender,
        )
    )


def make_workflow_event_notification_envelope(
    *,
    event: Mapping[str, Any],
    recipient: AgentChatRecipient,
    sender: AgentRuntimeActor,
) -> AgentRuntimeNotificationEnvelope:
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
            content=f"Workflow event {kind} is {state}.",
            metadata={
                "chat_id": chat_id,
                "event_id": event_id,
                "kind": kind,
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
