from __future__ import annotations

import inspect

from backend.web.routers import threads as threads_router
from backend.web.services import chat_delivery_hook


def test_delivery_paths_depend_on_agent_runtime_port_not_native_gateway() -> None:
    delivery_source = inspect.getsource(chat_delivery_hook)
    threads_source = inspect.getsource(threads_router)

    assert "NativeAgentRuntimeGateway" not in delivery_source
    assert "NativeAgentRuntimeGateway" not in threads_source
    assert "get_agent_runtime_gateway" in delivery_source
    assert "get_agent_runtime_gateway" in threads_source
