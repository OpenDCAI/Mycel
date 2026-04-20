from __future__ import annotations

import importlib
import inspect
from typing import get_type_hints


def test_agent_runtime_protocol_types_live_outside_web_service_layer() -> None:
    protocol_module = importlib.import_module("backend.protocols.agent_runtime")
    gateway_module = importlib.import_module("backend.agent_runtime.gateway")

    assert protocol_module.AgentChatDeliveryEnvelope.__module__ == "backend.protocols.agent_runtime"
    assert protocol_module.AgentThreadInputEnvelope.__module__ == "backend.protocols.agent_runtime"
    assert protocol_module.AgentChatDeliveryResult.__module__ == "backend.protocols.agent_runtime"
    assert not hasattr(protocol_module, "AgentGatewayDeliveryResult")
    assert not hasattr(gateway_module, "AgentChatDeliveryEnvelope")
    assert not hasattr(gateway_module, "AgentThreadInputEnvelope")
    assert not hasattr(gateway_module, "AgentChatDeliveryResult")


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


def test_agent_chat_recipient_supports_optional_preselected_thread_id() -> None:
    protocol_module = importlib.import_module("backend.protocols.agent_runtime")

    recipient_fields = get_type_hints(protocol_module.AgentChatRecipient)

    assert recipient_fields["thread_id"] == str | None


def test_agent_runtime_thread_input_result_is_a_protocol_object() -> None:
    protocol_module = importlib.import_module("backend.protocols.agent_runtime")
    gateway_module = importlib.import_module("backend.agent_runtime.gateway")
    port_module = importlib.import_module("backend.agent_runtime.port")

    gateway_hints = get_type_hints(gateway_module.NativeAgentRuntimeGateway.dispatch_thread_input)
    port_hints = get_type_hints(port_module.AgentRuntimeGatewayPort.dispatch_thread_input)

    assert protocol_module.AgentThreadInputResult.__module__ == "backend.protocols.agent_runtime"
    assert gateway_hints["return"] is protocol_module.AgentThreadInputResult
    assert port_hints["return"] is protocol_module.AgentThreadInputResult


def test_agent_runtime_gateway_handler_injection_is_typed() -> None:
    gateway_module = importlib.import_module("backend.agent_runtime.gateway")

    constructor_hints = get_type_hints(gateway_module.NativeAgentRuntimeGateway.__init__)

    assert "app" not in constructor_hints
    assert "AgentChatRuntimeHandler" in str(constructor_hints["chat_handlers"])
    assert constructor_hints["thread_input_handler"] == gateway_module.AgentThreadInputRuntimeHandler | None


def test_agent_runtime_implementation_lives_under_backend_agent_runtime() -> None:
    gateway_impl = importlib.import_module("backend.agent_runtime.gateway")
    bootstrap_impl = importlib.import_module("backend.agent_runtime.bootstrap")
    port_impl = importlib.import_module("backend.agent_runtime.port")
    chat_handler_impl = importlib.import_module("backend.agent_runtime.chat_handler")
    thread_handler_impl = importlib.import_module("backend.agent_runtime.thread_handler")

    assert gateway_impl.NativeAgentRuntimeGateway.__module__ == "backend.agent_runtime.gateway"
    assert bootstrap_impl.build_agent_runtime_gateway.__module__ == "backend.agent_runtime.bootstrap"
    assert port_impl.get_agent_runtime_gateway.__module__ == "backend.agent_runtime.port"
    assert chat_handler_impl.NativeAgentChatDeliveryHandler.__module__ == "backend.agent_runtime.chat_handler"
    assert thread_handler_impl.NativeAgentThreadInputHandler.__module__ == "backend.agent_runtime.thread_handler"
    assert gateway_impl.NativeAgentRuntimeGateway is not None
    assert port_impl.get_agent_runtime_gateway is not None
    assert chat_handler_impl.NativeAgentChatDeliveryHandler is not None
    assert thread_handler_impl.NativeAgentThreadInputHandler is not None


def test_chat_handler_depends_on_runtime_owned_services_not_web_imports() -> None:
    chat_handler_impl = importlib.import_module("backend.agent_runtime.chat_handler")
    bootstrap_impl = importlib.import_module("backend.agent_runtime.bootstrap")

    chat_handler_source = inspect.getsource(chat_handler_impl)
    bootstrap_source = inspect.getsource(bootstrap_impl)

    assert "backend.web.services.agent_pool" not in chat_handler_source
    assert "backend.web.services.streaming_service" not in chat_handler_source
    assert "self._app.state" not in chat_handler_source
    assert "count_unread" not in chat_handler_source
    assert "enqueue_chat_notification" not in chat_handler_source
    assert "format_chat_notification" not in chat_handler_source
    assert "list_by_agent_user" not in chat_handler_source
    assert "iter_agent_pool_items" not in chat_handler_source
    assert "AgentState" not in chat_handler_source
    assert "AppAgentChatRuntimeServices" in bootstrap_source
