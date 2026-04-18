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

    assert "NativeAgentRuntimeGateway" not in delivery_source
    assert "NativeAgentRuntimeGateway" not in threads_source
    assert "get_agent_runtime_gateway" in delivery_source
    assert "get_agent_runtime_gateway" in threads_source


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
        chat_id="chat-1",
        sender_id="human-user-1",
        sender_avatar_url=None,
        signal=None,
    )

    with pytest.raises(RuntimeError, match="runtime gateway down"):
        await asyncio.to_thread(deliver, request)
