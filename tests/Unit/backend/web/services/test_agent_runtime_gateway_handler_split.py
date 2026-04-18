from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from backend.protocols.agent_runtime import AgentGatewayDeliveryResult
from backend.web.services.agent_runtime_gateway import NativeAgentRuntimeGateway


@dataclass
class _FakeChatHandler:
    called_with: object | None = None

    async def dispatch(self, envelope):
        self.called_with = envelope
        return AgentGatewayDeliveryResult(status="accepted", thread_id="thread-1")


@dataclass
class _FakeThreadInputHandler:
    called_with: object | None = None

    async def dispatch(self, envelope):
        self.called_with = envelope
        return {"status": "started", "thread_id": "thread-1"}


@pytest.mark.asyncio
async def test_gateway_delegates_chat_and_thread_input_to_split_handlers() -> None:
    from backend.protocols.agent_runtime import (
        AgentChatContext,
        AgentChatDeliveryEnvelope,
        AgentChatRecipient,
        AgentRuntimeActor,
        AgentRuntimeMessage,
        AgentThreadInputEnvelope,
    )

    chat_handler = _FakeChatHandler()
    thread_input_handler = _FakeThreadInputHandler()
    gateway = NativeAgentRuntimeGateway(
        app=object(),
        chat_handlers={"mycel": chat_handler},
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

    chat_result = await gateway.dispatch_chat(chat_envelope)
    thread_result = await gateway.dispatch_thread_input(thread_envelope)

    assert chat_result == AgentGatewayDeliveryResult(status="accepted", thread_id="thread-1")
    assert thread_result == {"status": "started", "thread_id": "thread-1"}
    assert chat_handler.called_with is chat_envelope
    assert thread_input_handler.called_with is thread_envelope


def test_split_handler_modules_are_the_behavior_owners() -> None:
    from backend.web.services.agent_runtime_chat_handler import NativeAgentChatDeliveryHandler
    from backend.web.services.agent_runtime_thread_handler import NativeAgentThreadInputHandler

    assert NativeAgentChatDeliveryHandler.__name__ == "NativeAgentChatDeliveryHandler"
    assert NativeAgentThreadInputHandler.__name__ == "NativeAgentThreadInputHandler"


def test_gateway_rejects_single_chat_handler_entrypoint() -> None:
    constructor: Any = NativeAgentRuntimeGateway
    with pytest.raises(TypeError, match="chat_handler"):
        constructor(
            app=object(),
            chat_handler=_FakeChatHandler(),
            thread_input_handler=_FakeThreadInputHandler(),
        )


@pytest.mark.asyncio
async def test_gateway_routes_chat_delivery_by_runtime_source() -> None:
    from backend.protocols.agent_runtime import (
        AgentChatContext,
        AgentChatDeliveryEnvelope,
        AgentChatRecipient,
        AgentRuntimeActor,
        AgentRuntimeMessage,
    )

    external_handler = _FakeChatHandler()
    gateway = NativeAgentRuntimeGateway(
        app=object(),
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

    assert result == AgentGatewayDeliveryResult(status="accepted", thread_id="thread-1")
    assert external_handler.called_with is envelope


@pytest.mark.asyncio
async def test_gateway_rejects_unregistered_chat_runtime_source() -> None:
    from backend.protocols.agent_runtime import (
        AgentChatContext,
        AgentChatDeliveryEnvelope,
        AgentChatRecipient,
        AgentRuntimeActor,
        AgentRuntimeMessage,
    )

    gateway = NativeAgentRuntimeGateway(
        app=object(),
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
