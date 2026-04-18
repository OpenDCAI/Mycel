from __future__ import annotations

from dataclasses import dataclass

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
        AgentChatActor,
        AgentChatContext,
        AgentChatDeliveryEnvelope,
        AgentChatMessage,
        AgentChatRecipient,
        AgentThreadInputEnvelope,
    )

    chat_handler = _FakeChatHandler()
    thread_input_handler = _FakeThreadInputHandler()
    gateway = NativeAgentRuntimeGateway(
        app=object(),
        chat_handler=chat_handler,
        thread_input_handler=thread_input_handler,
    )
    chat_envelope = AgentChatDeliveryEnvelope(
        chat=AgentChatContext(chat_id="chat-1"),
        sender=AgentChatActor(user_id="human-1", user_type="human", display_name="Human"),
        recipient=AgentChatRecipient(agent_user_id="agent-1", runtime_source="mycel"),
        message=AgentChatMessage(content="hello"),
    )
    thread_envelope = AgentThreadInputEnvelope(thread_id="thread-1", content="hello")

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
