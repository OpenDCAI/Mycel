from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from backend.threads.chat_adapters.gateway import NativeAgentRuntimeGateway
from protocols.agent_runtime import AgentRuntimeNotificationResult, AgentThreadInputResult


@dataclass
class _FakeThreadInputHandler:
    called_with: object | None = None

    async def dispatch(self, envelope):
        self.called_with = envelope
        return AgentThreadInputResult(status="started", routing="direct", thread_id="thread-1")


@dataclass
class _FakeNotificationHandler:
    called_with: object | None = None

    async def dispatch_notification(self, envelope):
        self.called_with = envelope
        return AgentRuntimeNotificationResult(status="accepted", thread_id="thread-1")


@pytest.mark.asyncio
async def test_gateway_delegates_notifications_and_thread_input_to_split_handlers() -> None:
    from protocols.agent_runtime import (
        AgentChatRecipient,
        AgentRuntimeActor,
        AgentRuntimeMessage,
        AgentRuntimeNotificationEnvelope,
        AgentThreadInputEnvelope,
    )

    thread_input_handler = _FakeThreadInputHandler()
    gateway = NativeAgentRuntimeGateway(
        thread_input_handler=thread_input_handler,
    )
    thread_envelope = AgentThreadInputEnvelope(
        thread_id="thread-1",
        sender=AgentRuntimeActor(user_id="human-1", user_type="human", display_name="Owner", source="owner"),
        message=AgentRuntimeMessage(content="hello"),
    )
    notification_envelope = AgentRuntimeNotificationEnvelope(
        event_type="relationship.requested",
        recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="mycel", thread_id="thread-1"),
        sender=AgentRuntimeActor(user_id="human-1", user_type="human", display_name="Owner", source="relationship"),
        message=AgentRuntimeMessage(content="hello"),
        notification_type="relationship",
    )

    notification_result = await gateway.dispatch_notification(notification_envelope)
    notification_thread_input = thread_input_handler.called_with
    thread_result = await gateway.dispatch_thread_input(thread_envelope)

    assert notification_result == AgentRuntimeNotificationResult(status="accepted", thread_id="thread-1")
    assert thread_result == AgentThreadInputResult(status="started", routing="direct", thread_id="thread-1")
    assert isinstance(notification_thread_input, AgentThreadInputEnvelope)
    assert notification_thread_input.thread_id == "thread-1"
    assert notification_thread_input.sender is notification_envelope.sender
    assert notification_thread_input.message.content == notification_envelope.message.content
    assert thread_input_handler.called_with is thread_envelope


def test_gateway_rejects_single_chat_handler_entrypoint() -> None:
    constructor: Any = NativeAgentRuntimeGateway
    with pytest.raises(TypeError, match="chat_handler"):
        constructor(
            chat_handler=object(),
            thread_input_handler=_FakeThreadInputHandler(),
        )


@pytest.mark.asyncio
async def test_gateway_routes_external_notifications_by_runtime_source() -> None:
    from protocols.agent_runtime import (
        AgentChatRecipient,
        AgentRuntimeActor,
        AgentRuntimeMessage,
        AgentRuntimeNotificationEnvelope,
    )

    handler = _FakeNotificationHandler()
    gateway = NativeAgentRuntimeGateway(
        notification_handlers={"external": handler},
        thread_input_handler=_FakeThreadInputHandler(),
    )
    envelope = AgentRuntimeNotificationEnvelope(
        event_type="relationship.requested",
        recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="external"),
        sender=AgentRuntimeActor(user_id="human-1", user_type="human", display_name="Human"),
        message=AgentRuntimeMessage(content="hello"),
        notification_type="relationship",
    )

    result = await gateway.dispatch_notification(envelope)

    assert result == AgentRuntimeNotificationResult(status="accepted", thread_id="thread-1")
    assert handler.called_with is envelope


@pytest.mark.asyncio
async def test_gateway_rejects_unregistered_notification_runtime_source() -> None:
    from protocols.agent_runtime import (
        AgentChatRecipient,
        AgentRuntimeActor,
        AgentRuntimeMessage,
        AgentRuntimeNotificationEnvelope,
    )

    gateway = NativeAgentRuntimeGateway(
        notification_handlers={"mycel": _FakeNotificationHandler()},
        thread_input_handler=_FakeThreadInputHandler(),
    )
    envelope = AgentRuntimeNotificationEnvelope(
        event_type="relationship.requested",
        recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="external-hook"),
        sender=AgentRuntimeActor(user_id="human-1", user_type="human", display_name="Human"),
        message=AgentRuntimeMessage(content="hello"),
        notification_type="relationship",
    )

    with pytest.raises(ValueError, match="No Agent runtime notification handler registered for runtime_source='external-hook'"):
        await gateway.dispatch_notification(envelope)


@pytest.mark.asyncio
async def test_gateway_converts_managed_notification_to_thread_input_at_runtime_boundary() -> None:
    from protocols.agent_runtime import (
        AgentChatRecipient,
        AgentRuntimeActor,
        AgentRuntimeMessage,
        AgentRuntimeNotificationEnvelope,
        AgentRuntimeTransport,
        AgentThreadInputEnvelope,
    )

    handler = _FakeThreadInputHandler()
    gateway = NativeAgentRuntimeGateway(thread_input_handler=handler)
    envelope = AgentRuntimeNotificationEnvelope(
        event_type="relationship.requested",
        recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="mycel", thread_id="thread-1"),
        sender=AgentRuntimeActor(user_id="human-1", user_type="human", display_name="Human", source="relationship"),
        message=AgentRuntimeMessage(content="hello", metadata={"relationship_id": "rel-1"}),
        notification_type="relationship",
        transport=AgentRuntimeTransport(
            delivery_id="delivery-1",
            correlation_id="corr-1",
            idempotency_key="idem-1",
        ),
    )

    result = await gateway.dispatch_notification(envelope)

    assert result == AgentRuntimeNotificationResult(status="accepted", thread_id="thread-1")
    called = handler.called_with
    assert isinstance(called, AgentThreadInputEnvelope)
    assert called.thread_id == "thread-1"
    assert called.sender is envelope.sender
    assert called.message.content == envelope.message.content
    assert called.message.metadata == {
        "relationship_id": "rel-1",
        "event_type": "relationship.requested",
        "notification_type": "relationship",
        "runtime_protocol_version": "agent.runtime.notification.v1",
        "delivery_id": "delivery-1",
        "correlation_id": "corr-1",
        "idempotency_key": "idem-1",
    }
    assert called.transport is envelope.transport
