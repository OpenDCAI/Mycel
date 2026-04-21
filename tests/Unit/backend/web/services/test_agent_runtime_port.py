from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_agent_runtime_port_requires_lifespan_registration() -> None:
    from backend.threads.chat_adapters.port import get_agent_runtime_gateway

    with pytest.raises(AttributeError, match="threads_runtime_state"):
        get_agent_runtime_gateway(SimpleNamespace(state=SimpleNamespace()))


def test_agent_runtime_port_reads_gateway_from_threads_runtime_state() -> None:
    from backend.threads.chat_adapters.port import get_agent_runtime_gateway

    gateway = object()
    app = SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(agent_runtime_gateway=gateway)))

    assert get_agent_runtime_gateway(app) is gateway
