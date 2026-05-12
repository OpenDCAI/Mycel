from __future__ import annotations

import importlib
from pathlib import Path
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


def test_chat_inlets_do_not_dispatch_runtime_gateway_directly() -> None:
    repo_root = Path(__file__).parents[5]
    inlet_files = list((repo_root / "backend" / "threads" / "chat_adapters").glob("*_inlet.py"))

    assert inlet_files

    for path in inlet_files:
        text = path.read_text(encoding="utf-8")
        assert "get_agent_runtime_gateway" not in text, path
        assert ".dispatch_chat(" not in text, path
        assert ".dispatch_notification(" not in text, path
        assert "AgentChatDeliveryEnvelope" not in text, path
        assert "AgentRuntimeNotificationEnvelope" not in text, path


def test_chat_inlets_do_not_compose_planned_runtime_events_directly() -> None:
    repo_root = Path(__file__).parents[5]
    inlet_files = list((repo_root / "backend" / "threads" / "chat_adapters").glob("*_inlet.py"))

    assert inlet_files

    for path in inlet_files:
        text = path.read_text(encoding="utf-8")
        assert "runtime_event_hook" not in text, path
        assert "runtime_event_runner" not in text, path
        assert "make_planned_runtime_event_hook" not in text, path
        assert "run_planned_runtime_event" not in text, path


def test_thread_router_does_not_import_runtime_thread_input_actions_directly() -> None:
    repo_root = Path(__file__).parents[5]
    router_path = repo_root / "backend" / "web" / "routers" / "threads.py"

    text = router_path.read_text(encoding="utf-8")

    assert "runtime_thread_input_action" not in text


def test_thread_run_lifecycle_does_not_import_runtime_thread_input_actions_directly() -> None:
    repo_root = Path(__file__).parents[5]
    run_files = [
        repo_root / "backend" / "threads" / "run" / "cancellation.py",
        repo_root / "backend" / "threads" / "run" / "followups.py",
    ]

    for path in run_files:
        text = path.read_text(encoding="utf-8")
        assert "runtime_thread_input_action" not in text, path


def test_runtime_actions_use_shared_actor_builder() -> None:
    repo_root = Path(__file__).parents[5]
    action_files = list((repo_root / "backend" / "threads" / "chat_adapters").glob("runtime_*_action.py"))

    assert action_files

    for path in action_files:
        text = path.read_text(encoding="utf-8")
        assert "AgentRuntimeActor" not in text, path


def test_runtime_action_adapters_do_not_export_unused_single_dispatch_helpers() -> None:
    chat_action_module = importlib.import_module("backend.threads.chat_adapters.runtime_chat_delivery_action")
    notification_action_module = importlib.import_module("backend.threads.chat_adapters.runtime_notification_action")

    assert not hasattr(chat_action_module, "dispatch_runtime_chat_delivery_action")
    assert not hasattr(notification_action_module, "dispatch_runtime_notification_action")


def test_runtime_action_adapters_do_not_export_envelope_dispatch_helpers() -> None:
    chat_action_module = importlib.import_module("backend.threads.chat_adapters.runtime_chat_delivery_action")
    notification_action_module = importlib.import_module("backend.threads.chat_adapters.runtime_notification_action")
    thread_input_action_module = importlib.import_module("backend.threads.chat_adapters.runtime_thread_input_action")

    assert not hasattr(chat_action_module, "dispatch_runtime_chat_delivery_envelopes")
    assert not hasattr(notification_action_module, "dispatch_runtime_notification_envelopes")
    assert not hasattr(thread_input_action_module, "dispatch_runtime_thread_input_envelopes")


def test_runtime_action_adapters_do_not_export_batch_envelope_planners() -> None:
    chat_action_module = importlib.import_module("backend.threads.chat_adapters.runtime_chat_delivery_action")
    notification_action_module = importlib.import_module("backend.threads.chat_adapters.runtime_notification_action")
    thread_input_action_module = importlib.import_module("backend.threads.chat_adapters.runtime_thread_input_action")

    assert not hasattr(chat_action_module, "plan_runtime_chat_delivery_envelopes")
    assert not hasattr(notification_action_module, "plan_runtime_notification_envelopes")
    assert not hasattr(thread_input_action_module, "plan_runtime_thread_input_envelopes")


def test_runtime_action_adapters_do_not_export_concrete_event_dispatch_helpers() -> None:
    chat_action_module = importlib.import_module("backend.threads.chat_adapters.runtime_chat_delivery_action")
    notification_action_module = importlib.import_module("backend.threads.chat_adapters.runtime_notification_action")
    chat_inlet_module = importlib.import_module("backend.threads.chat_adapters.chat_inlet")

    assert not hasattr(chat_action_module, "dispatch_runtime_chat_delivery_event")
    assert not hasattr(notification_action_module, "dispatch_runtime_notification_event")
    assert not hasattr(chat_inlet_module, "dispatch_chat_delivery_event")


def test_runtime_protocol_envelopes_are_constructed_only_at_adapter_boundaries() -> None:
    repo_root = Path(__file__).parents[5]
    backend_files = list((repo_root / "backend").rglob("*.py"))
    allowed = {
        repo_root / "backend" / "threads" / "chat_adapters" / "runtime_chat_delivery_action.py",
        repo_root / "backend" / "threads" / "chat_adapters" / "runtime_metadata.py",
        repo_root / "backend" / "threads" / "chat_adapters" / "runtime_notification_action.py",
        repo_root / "backend" / "threads" / "chat_adapters" / "runtime_thread_input_action.py",
    }

    assert backend_files

    for path in backend_files:
        text = path.read_text(encoding="utf-8")
        constructs_envelope = (
            "AgentChatDeliveryEnvelope(" in text or "AgentRuntimeNotificationEnvelope(" in text or "AgentThreadInputEnvelope(" in text
        )
        if constructs_envelope:
            assert path in allowed, path
