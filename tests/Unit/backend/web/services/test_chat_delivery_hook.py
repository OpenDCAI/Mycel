from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

from backend.web.routers import threads as threads_router
from backend.web.services import chat_delivery_hook
from messaging.delivery.dispatcher import ChatDeliveryRequest


def test_delivery_paths_depend_on_agent_runtime_port_not_native_gateway() -> None:
    delivery_source = inspect.getsource(chat_delivery_hook)
    threads_source = inspect.getsource(threads_router)
    from backend.web.core import lifespan as lifespan_module

    lifespan_source = inspect.getsource(lifespan_module)

    assert "NativeAgentRuntimeGateway" not in delivery_source
    assert "NativeAgentRuntimeGateway" not in threads_source
    assert "get_agent_runtime_gateway" in delivery_source
    assert "get_agent_runtime_gateway" in threads_source
    assert "backend.agent_runtime.port" in delivery_source
    assert "backend.agent_runtime.port" in threads_source
    assert "backend.web.services.agent_runtime_port" not in delivery_source
    assert "backend.web.services.agent_runtime_port" not in threads_source
    assert "backend.agent_runtime.gateway" in lifespan_source
    assert "backend.web.services.agent_runtime_gateway" not in lifespan_source


@pytest.mark.asyncio
async def test_chat_delivery_hook_propagates_runtime_gateway_failures() -> None:
    class FailingGateway:
        async def dispatch_chat(self, _envelope):
            raise RuntimeError("runtime gateway down")

    app = SimpleNamespace(state=SimpleNamespace(agent_runtime_gateway=FailingGateway()))
    deliver = chat_delivery_hook.make_chat_delivery_fn(app)
    request = ChatDeliveryRequest(
        recipient_id="agent-user-1",
        recipient_user=SimpleNamespace(id="agent-user-1", type="agent"),
        content="hello",
        sender_name="Human",
        sender_type="human",
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        signal=None,
    )

    with pytest.raises(RuntimeError, match="runtime gateway down"):
        await asyncio.to_thread(deliver, request)


@pytest.mark.asyncio
async def test_chat_delivery_hook_uses_request_sender_type() -> None:
    class RecordingGateway:
        envelope = None

        async def dispatch_chat(self, envelope):
            self.envelope = envelope

    gateway = RecordingGateway()
    app = SimpleNamespace(state=SimpleNamespace(agent_runtime_gateway=gateway))
    deliver = chat_delivery_hook.make_chat_delivery_fn(app)
    request = ChatDeliveryRequest(
        recipient_id="agent-user-1",
        recipient_user=SimpleNamespace(id="agent-user-1", type="agent"),
        content="hello",
        sender_name="Human",
        sender_type="human",
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        signal=None,
    )

    await asyncio.to_thread(deliver, request)

    assert gateway.envelope is not None
    assert gateway.envelope.sender.user_type == "human"


@pytest.mark.asyncio
async def test_chat_delivery_hook_requires_recipient_user_type() -> None:
    class RecordingGateway:
        called = False

        async def dispatch_chat(self, _envelope):
            self.called = True

    gateway = RecordingGateway()
    app = SimpleNamespace(state=SimpleNamespace(agent_runtime_gateway=gateway))
    deliver = chat_delivery_hook.make_chat_delivery_fn(app)
    request = ChatDeliveryRequest(
        recipient_id="agent-user-1",
        recipient_user=SimpleNamespace(id="agent-user-1"),
        content="hello",
        sender_name="Human",
        sender_type="human",
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        signal=None,
    )

    with pytest.raises(RuntimeError, match="Chat delivery recipient is missing user type: agent-user-1"):
        await asyncio.to_thread(deliver, request)

    assert gateway.called is False


@pytest.mark.asyncio
async def test_chat_delivery_hook_requires_recipient_user_id() -> None:
    class RecordingGateway:
        called = False

        async def dispatch_chat(self, _envelope):
            self.called = True

    gateway = RecordingGateway()
    app = SimpleNamespace(state=SimpleNamespace(agent_runtime_gateway=gateway))
    deliver = chat_delivery_hook.make_chat_delivery_fn(app)
    request = ChatDeliveryRequest(
        recipient_id="agent-user-1",
        recipient_user=SimpleNamespace(type="agent"),
        content="hello",
        sender_name="Human",
        sender_type="human",
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        signal=None,
    )

    with pytest.raises(RuntimeError, match="Chat delivery recipient is missing user id: agent-user-1"):
        await asyncio.to_thread(deliver, request)

    assert gateway.called is False
