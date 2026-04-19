from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_agent_runtime_port_requires_lifespan_registration() -> None:
    from backend.agent_runtime.port import get_agent_runtime_gateway

    with pytest.raises(AttributeError, match="agent_runtime_gateway"):
        get_agent_runtime_gateway(SimpleNamespace(state=SimpleNamespace()))
