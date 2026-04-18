from __future__ import annotations

import importlib
from typing import get_type_hints


def test_agent_runtime_protocol_types_live_outside_web_service_layer() -> None:
    protocol_module = importlib.import_module("backend.protocols.agent_runtime")
    gateway_module = importlib.import_module("backend.web.services.agent_runtime_gateway")

    assert protocol_module.AgentChatDeliveryEnvelope.__module__ == "backend.protocols.agent_runtime"
    assert protocol_module.AgentThreadInputEnvelope.__module__ == "backend.protocols.agent_runtime"
    assert not hasattr(gateway_module, "AgentChatDeliveryEnvelope")
    assert not hasattr(gateway_module, "AgentThreadInputEnvelope")


def test_agent_runtime_chat_and_thread_inputs_share_message_protocol_objects() -> None:
    protocol_module = importlib.import_module("backend.protocols.agent_runtime")

    chat_fields = get_type_hints(protocol_module.AgentChatDeliveryEnvelope)
    thread_fields = get_type_hints(protocol_module.AgentThreadInputEnvelope)

    assert chat_fields["sender"] is protocol_module.AgentRuntimeActor
    assert chat_fields["message"] is protocol_module.AgentRuntimeMessage
    assert chat_fields["transport"] is protocol_module.AgentRuntimeTransport
    assert thread_fields["sender"] is protocol_module.AgentRuntimeActor
    assert thread_fields["message"] is protocol_module.AgentRuntimeMessage
    assert thread_fields["transport"] is protocol_module.AgentRuntimeTransport
    assert "content" not in thread_fields
    assert "source" not in thread_fields
    assert "message_metadata" not in thread_fields


def test_agent_runtime_thread_input_result_is_a_protocol_object() -> None:
    protocol_module = importlib.import_module("backend.protocols.agent_runtime")
    gateway_module = importlib.import_module("backend.web.services.agent_runtime_gateway")
    port_module = importlib.import_module("backend.web.services.agent_runtime_port")

    gateway_hints = get_type_hints(gateway_module.NativeAgentRuntimeGateway.dispatch_thread_input)
    port_hints = get_type_hints(port_module.AgentRuntimeGatewayPort.dispatch_thread_input)

    assert protocol_module.AgentThreadInputResult.__module__ == "backend.protocols.agent_runtime"
    assert gateway_hints["return"] is protocol_module.AgentThreadInputResult
    assert port_hints["return"] is protocol_module.AgentThreadInputResult
