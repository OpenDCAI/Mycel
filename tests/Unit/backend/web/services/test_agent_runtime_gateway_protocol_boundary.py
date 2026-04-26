from __future__ import annotations

import importlib
from typing import get_type_hints


def test_agent_runtime_chat_and_thread_inputs_share_message_protocol_objects() -> None:
    protocol_module = importlib.import_module("protocols.agent_runtime")

    chat_fields = get_type_hints(protocol_module.AgentChatDeliveryEnvelope)
    thread_fields = get_type_hints(protocol_module.AgentThreadInputEnvelope)

    assert chat_fields["sender"] is protocol_module.AgentRuntimeActor
    assert chat_fields["message"] is protocol_module.AgentRuntimeMessage
    assert chat_fields["transport"] is protocol_module.AgentRuntimeTransport
    assert chat_fields["wake"] is bool
    assert thread_fields["sender"] is protocol_module.AgentRuntimeActor
    assert thread_fields["message"] is protocol_module.AgentRuntimeMessage
    assert thread_fields["transport"] is protocol_module.AgentRuntimeTransport
    assert "content" not in thread_fields
    assert "source" not in thread_fields
    assert "message_metadata" not in thread_fields


def test_agent_chat_recipient_supports_optional_preselected_thread_id() -> None:
    protocol_module = importlib.import_module("protocols.agent_runtime")

    recipient_fields = get_type_hints(protocol_module.AgentChatRecipient)

    assert recipient_fields["thread_id"] == str | None


def test_agent_runtime_thread_input_result_is_a_protocol_object() -> None:
    protocol_module = importlib.import_module("protocols.agent_runtime")
    gateway_module = importlib.import_module("backend.threads.chat_adapters.gateway")
    port_module = importlib.import_module("backend.threads.chat_adapters.port")

    gateway_hints = get_type_hints(gateway_module.NativeAgentRuntimeGateway.dispatch_thread_input)
    port_hints = get_type_hints(port_module.AgentRuntimeGatewayPort.dispatch_thread_input)

    assert gateway_hints["return"] is protocol_module.AgentThreadInputResult
    assert port_hints["return"] is protocol_module.AgentThreadInputResult


def test_agent_runtime_gateway_handler_injection_is_typed() -> None:
    gateway_module = importlib.import_module("backend.threads.chat_adapters.gateway")

    constructor_hints = get_type_hints(gateway_module.NativeAgentRuntimeGateway.__init__)

    assert "app" not in constructor_hints
    assert "AgentChatRuntimeHandler" in str(constructor_hints["chat_handlers"])
    assert constructor_hints["thread_input_handler"] == gateway_module.AgentThreadInputRuntimeHandler | None
