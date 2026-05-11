from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from backend.threads.chat_adapters.gateway import NativeAgentRuntimeGateway
from backend.threads.chat_adapters.notification_handler import NativeAgentNotificationHandler
from protocols.agent_runtime import AgentChatDeliveryResult, AgentRuntimeNotificationResult, AgentThreadInputResult


@dataclass
class _FakeChatHandler:
    called_with: object | None = None

    async def dispatch(self, envelope):
        self.called_with = envelope
        return AgentChatDeliveryResult(status="accepted", thread_id="thread-1")


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
async def test_gateway_delegates_chat_and_thread_input_to_split_handlers() -> None:
    from protocols.agent_runtime import (
        AgentChatContext,
        AgentChatDeliveryEnvelope,
        AgentChatRecipient,
        AgentRuntimeActor,
        AgentRuntimeMessage,
        AgentRuntimeNotificationEnvelope,
        AgentThreadInputEnvelope,
    )

    chat_handler = _FakeChatHandler()
    notification_handler = _FakeNotificationHandler()
    thread_input_handler = _FakeThreadInputHandler()
    gateway = NativeAgentRuntimeGateway(
        chat_handlers={"mycel": chat_handler},
        notification_handlers={"mycel": notification_handler},
        thread_input_handler=thread_input_handler,
    )
    chat_envelope = AgentChatDeliveryEnvelope(
        chat=AgentChatContext(chat_id="chat-1"),
        sender=AgentRuntimeActor(user_id="human-1", user_type="human", display_name="Human"),
        recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="mycel"),
        message=AgentRuntimeMessage(content="hello"),
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

    chat_result = await gateway.dispatch_chat(chat_envelope)
    notification_result = await gateway.dispatch_notification(notification_envelope)
    thread_result = await gateway.dispatch_thread_input(thread_envelope)

    assert chat_result == AgentChatDeliveryResult(status="accepted", thread_id="thread-1")
    assert notification_result == AgentRuntimeNotificationResult(status="accepted", thread_id="thread-1")
    assert thread_result == AgentThreadInputResult(status="started", routing="direct", thread_id="thread-1")
    assert chat_handler.called_with is chat_envelope
    assert notification_handler.called_with is notification_envelope
    assert thread_input_handler.called_with is thread_envelope


def test_gateway_rejects_single_chat_handler_entrypoint() -> None:
    constructor: Any = NativeAgentRuntimeGateway
    with pytest.raises(TypeError, match="chat_handler"):
        constructor(
            chat_handler=_FakeChatHandler(),
            thread_input_handler=_FakeThreadInputHandler(),
        )


@pytest.mark.asyncio
async def test_gateway_routes_chat_delivery_by_runtime_source() -> None:
    from protocols.agent_runtime import (
        AgentChatContext,
        AgentChatDeliveryEnvelope,
        AgentChatRecipient,
        AgentRuntimeActor,
        AgentRuntimeMessage,
    )

    external_handler = _FakeChatHandler()
    gateway = NativeAgentRuntimeGateway(
        chat_handlers={"external-hook": external_handler},
        thread_input_handler=_FakeThreadInputHandler(),
    )
    envelope = AgentChatDeliveryEnvelope(
        chat=AgentChatContext(chat_id="chat-1"),
        sender=AgentRuntimeActor(user_id="human-1", user_type="human", display_name="Human"),
        recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="external-hook"),
        message=AgentRuntimeMessage(content="hello"),
    )

    result = await gateway.dispatch_chat(envelope)

    assert result == AgentChatDeliveryResult(status="accepted", thread_id="thread-1")
    assert external_handler.called_with is envelope


@pytest.mark.asyncio
async def test_gateway_rejects_unregistered_chat_runtime_source() -> None:
    from protocols.agent_runtime import (
        AgentChatContext,
        AgentChatDeliveryEnvelope,
        AgentChatRecipient,
        AgentRuntimeActor,
        AgentRuntimeMessage,
    )

    gateway = NativeAgentRuntimeGateway(
        chat_handlers={"mycel": _FakeChatHandler()},
        thread_input_handler=_FakeThreadInputHandler(),
    )
    envelope = AgentChatDeliveryEnvelope(
        chat=AgentChatContext(chat_id="chat-1"),
        sender=AgentRuntimeActor(user_id="human-1", user_type="human", display_name="Human"),
        recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="external-hook"),
        message=AgentRuntimeMessage(content="hello"),
    )

    with pytest.raises(ValueError, match="No Agent chat runtime handler registered for runtime_source='external-hook'"):
        await gateway.dispatch_chat(envelope)


@pytest.mark.asyncio
async def test_gateway_routes_notifications_by_runtime_source() -> None:
    from protocols.agent_runtime import (
        AgentChatRecipient,
        AgentRuntimeActor,
        AgentRuntimeMessage,
        AgentRuntimeNotificationEnvelope,
    )

    handler = _FakeNotificationHandler()
    gateway = NativeAgentRuntimeGateway(
        notification_handlers={"mycel": handler},
        thread_input_handler=_FakeThreadInputHandler(),
    )
    envelope = AgentRuntimeNotificationEnvelope(
        event_type="relationship.requested",
        recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="mycel", thread_id="thread-1"),
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
async def test_native_notification_handler_converts_to_thread_input_at_runtime_boundary() -> None:
    from protocols.agent_runtime import (
        AgentChatRecipient,
        AgentRuntimeActor,
        AgentRuntimeMessage,
        AgentRuntimeNotificationEnvelope,
        AgentRuntimeTransport,
    )

    thread_input_handler = _FakeThreadInputHandler()
    handler = NativeAgentNotificationHandler(thread_input_handler=thread_input_handler)
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

    result = await handler.dispatch_notification(envelope)

    assert result == AgentRuntimeNotificationResult(status="accepted", thread_id="thread-1")
    assert thread_input_handler.called_with is not None
    assert thread_input_handler.called_with.thread_id == "thread-1"
    assert thread_input_handler.called_with.sender is envelope.sender
    assert thread_input_handler.called_with.message is envelope.message
    assert thread_input_handler.called_with.transport is envelope.transport
