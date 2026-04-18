from __future__ import annotations

import importlib


def test_agent_runtime_protocol_types_live_outside_web_service_layer() -> None:
    protocol_module = importlib.import_module("backend.protocols.agent_runtime")
    gateway_module = importlib.import_module("backend.web.services.agent_runtime_gateway")

    assert protocol_module.AgentChatDeliveryEnvelope.__module__ == "backend.protocols.agent_runtime"
    assert protocol_module.AgentThreadInputEnvelope.__module__ == "backend.protocols.agent_runtime"
    assert not hasattr(gateway_module, "AgentChatDeliveryEnvelope")
    assert not hasattr(gateway_module, "AgentThreadInputEnvelope")
