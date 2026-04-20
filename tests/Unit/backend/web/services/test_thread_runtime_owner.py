from __future__ import annotations

import importlib
import inspect


def test_thread_runtime_namespace_exports_binding_and_state_helpers() -> None:
    binding_owner = importlib.import_module("backend.thread_runtime.binding")
    state_owner = importlib.import_module("backend.thread_runtime.state")

    assert binding_owner.resolve_thread_runtime_binding is not None
    assert binding_owner.ThreadRuntimeBindingError is not None
    assert state_owner.get_sandbox_info is not None
    assert state_owner.get_sandbox_status_from_repos is not None
    assert "backend.web.services.thread_runtime_binding_service" not in inspect.getsource(state_owner)


def test_agent_pool_uses_thread_runtime_sandbox_owner() -> None:
    sandbox_owner = importlib.import_module("backend.thread_runtime.sandbox")
    agent_pool_module = importlib.import_module("backend.web.services.agent_pool")
    source = inspect.getsource(agent_pool_module)

    assert agent_pool_module.resolve_thread_sandbox is sandbox_owner.resolve_thread_sandbox
    assert "from backend.thread_runtime.sandbox import resolve_thread_sandbox" in source
    assert "def resolve_thread_sandbox(" not in source


def test_thread_runtime_history_uses_thread_runtime_message_repair_owner() -> None:
    history_source = inspect.getsource(importlib.import_module("backend.thread_runtime.history"))
    owner_module = importlib.import_module("backend.thread_runtime.interruption")

    assert owner_module.repair_interrupted_tool_call_messages is not None
    assert "from backend.thread_runtime.interruption import repair_interrupted_tool_call_messages" in history_source
    assert "backend.web.services.thread_message_interruption_service" not in history_source


def test_trace_read_service_uses_thread_runtime_history_owner() -> None:
    trace_source = inspect.getsource(importlib.import_module("backend.monitor.infrastructure.read_models.trace_read_service"))

    assert "from backend.thread_history import build_thread_history_transport, get_thread_history_payload" not in trace_source
    assert "from backend.thread_runtime.history import build_thread_history_transport, get_thread_history_payload" in trace_source


def test_thread_runtime_convergence_does_not_import_web_compat_shell() -> None:
    convergence_source = inspect.getsource(importlib.import_module("backend.thread_runtime.convergence"))

    assert "backend.web.services.thread_runtime_convergence" not in convergence_source


def test_thread_runtime_namespace_exports_owner_thread_reads() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.owner_reads")

    assert owner_module.list_owner_thread_rows_for_auth_burst is not None


def test_agent_pool_uses_thread_runtime_pool_factory_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.pool.factory")
    agent_pool_module = importlib.import_module("backend.web.services.agent_pool")
    source = inspect.getsource(agent_pool_module)

    assert owner_module.create_agent_sync is agent_pool_module.create_agent_sync
    assert "from backend.thread_runtime.pool.factory import create_agent_sync" in source
    assert "def create_agent_sync(" not in source


def test_agent_pool_uses_thread_runtime_pool_registry_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.pool.registry")
    agent_pool_module = importlib.import_module("backend.web.services.agent_pool")
    source = inspect.getsource(agent_pool_module)
    owner_source = inspect.getsource(owner_module)

    assert hasattr(agent_pool_module, "get_or_create_agent")
    assert hasattr(agent_pool_module, "update_agent_config")
    assert "from backend.thread_runtime.pool import registry as _registry" in source
    assert "async def get_or_create_agent(" in source
    assert "async def update_agent_config(" in source
    assert hasattr(agent_pool_module, "get_or_create_agent_id")
    assert hasattr(agent_pool_module, "get_file_channel_binding")
    assert owner_module.get_or_create_agent.__module__ == "backend.thread_runtime.pool.registry"
    assert owner_module.update_agent_config.__module__ == "backend.thread_runtime.pool.registry"
    assert "backend.web.services.file_channel_service" not in owner_source
    assert "from backend.file_channel import get_file_channel_binding" in source
    assert "backend.web.services.file_channel_service" not in source


def test_thread_launch_config_uses_thread_runtime_launch_config_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.launch_config")
    owner_source = inspect.getsource(owner_module)

    assert owner_module.normalize_launch_config_payload is not None
    assert owner_module.build_new_launch_config is not None
    assert owner_module.resolve_default_config is not None
    assert "sandbox_service.available_sandbox_types" not in owner_source
    assert "available_sandbox_types is None or list_library is None" in owner_source


def test_thread_runtime_pool_exports_idle_reaper_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.pool.idle_reaper")
    lifespan_source = inspect.getsource(importlib.import_module("backend.web.core.lifespan"))

    assert "backend.web.services.idle_reaper" not in lifespan_source
    assert "backend.thread_runtime.pool" in lifespan_source
    assert hasattr(owner_module, "run_idle_reaper_once")
    assert hasattr(owner_module, "idle_reaper_loop")
    assert owner_module.__name__ == "backend.thread_runtime.pool.idle_reaper"


def test_thread_visibility_uses_thread_projection_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.projection")

    assert owner_module.canonical_owner_threads is not None


def test_streaming_service_uses_thread_runtime_run_cancellation_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.cancellation")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))

    assert owner_module.persist_cancelled_run_input_if_missing is not None
    assert owner_module.flush_cancelled_owner_steers is not None
    assert owner_module.emit_queued_terminal_followups is not None
    assert "from backend.thread_runtime.run import cancellation as _run_cancellation" in streaming_source


def test_streaming_service_uses_thread_runtime_buffer_wiring_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.buffer_wiring")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))
    owner_source = inspect.getsource(owner_module)

    assert owner_module.get_or_create_thread_buffer is not None
    assert owner_module.ensure_thread_handlers is not None
    assert "from backend.thread_runtime.run import buffer_wiring as _run_buffer_wiring" in streaming_source
    assert "backend.web.services.event_buffer" not in owner_source
    assert "backend.web.services.streaming_service" not in owner_source
    assert "backend.web.services.event_store" not in owner_source


def test_thread_runtime_buffer_wiring_uses_neutral_event_bus_owner() -> None:
    owner_module = importlib.import_module("backend.event_bus")
    owner_source = inspect.getsource(importlib.import_module("backend.thread_runtime.run.buffer_wiring"))

    assert owner_module.EventBus is not None
    assert owner_module.get_event_bus is not None
    assert "from backend.event_bus import get_event_bus" in owner_source
    assert "backend.web.event_bus" not in owner_source


def test_streaming_service_uses_thread_runtime_run_lifecycle_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.lifecycle")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))

    assert owner_module.prime_sandbox is not None
    assert owner_module.write_cancellation_markers is not None
    assert owner_module.repair_incomplete_tool_calls is not None
    assert "from backend.thread_runtime.run import lifecycle as _run_lifecycle" in streaming_source


def test_streaming_service_uses_thread_runtime_run_entrypoints_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.entrypoints")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))

    assert owner_module.start_agent_run is not None
    assert owner_module.run_child_thread_live is not None
    assert "from backend.thread_runtime.run import entrypoints as _run_entrypoints" in streaming_source


def test_streaming_service_uses_thread_runtime_run_followups_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.followups")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))

    assert owner_module.consume_followup_queue is not None
    assert "from backend.thread_runtime.run import followups as _run_followups" in streaming_source


def test_streaming_service_uses_thread_runtime_sse_observer_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.observer")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))
    owner_source = inspect.getsource(owner_module)

    assert owner_module.observe_thread_events is not None
    assert owner_module.observe_run_events is not None
    assert owner_module.observe_sse_buffer is not None
    assert "from backend.thread_runtime.run import observer as _run_observer" in streaming_source
    assert "backend.web.services.event_buffer" not in owner_source


def test_streaming_service_uses_thread_runtime_trajectory_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.trajectory")
    execution_source = inspect.getsource(importlib.import_module("backend.thread_runtime.run.execution"))

    assert owner_module.build_trajectory_scope is not None
    assert "from backend.thread_runtime.run import trajectory as _run_trajectory" in execution_source


def test_streaming_service_uses_thread_runtime_observation_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.observation")
    execution_source = inspect.getsource(importlib.import_module("backend.thread_runtime.run.execution"))

    assert owner_module.build_observation is not None
    assert "from backend.thread_runtime.run import observation as _run_observation" in execution_source


def test_streaming_service_uses_thread_runtime_activity_bridge_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.activity_bridge")
    execution_source = inspect.getsource(importlib.import_module("backend.thread_runtime.run.execution"))

    assert owner_module.build_activity_bridge is not None
    assert "from backend.thread_runtime.run import activity_bridge as _run_activity_bridge" in execution_source


def test_streaming_service_uses_thread_runtime_emit_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.emit")
    execution_source = inspect.getsource(importlib.import_module("backend.thread_runtime.run.execution"))
    owner_source = inspect.getsource(owner_module)

    assert owner_module.build_emit is not None
    assert "from backend.thread_runtime.run import emit as _run_emit" in execution_source
    assert "backend.web.services.event_store" not in owner_source


def test_streaming_service_uses_thread_runtime_prologue_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.prologue")
    execution_source = inspect.getsource(importlib.import_module("backend.thread_runtime.run.execution"))

    assert owner_module.emit_run_prologue is not None
    assert "from backend.thread_runtime.run import prologue as _run_prologue" in execution_source


def test_streaming_service_uses_thread_runtime_input_construction_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.input_construction")
    execution_source = inspect.getsource(importlib.import_module("backend.thread_runtime.run.execution"))

    assert owner_module.build_initial_input is not None
    assert "from backend.thread_runtime.run import input_construction as _run_input_construction" in execution_source


def test_streaming_service_uses_thread_runtime_tool_call_dedup_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.tool_call_dedup")
    execution_source = inspect.getsource(importlib.import_module("backend.thread_runtime.run.execution"))

    assert owner_module.ToolCallDedup is not None
    assert "from backend.thread_runtime.run import tool_call_dedup as _run_tool_call_dedup" in execution_source


def test_streaming_service_uses_thread_runtime_stream_loop_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.stream_loop")
    execution_source = inspect.getsource(importlib.import_module("backend.thread_runtime.run.execution"))

    assert owner_module.run_stream_loop is not None
    assert "from backend.thread_runtime.run import stream_loop as _run_stream_loop" in execution_source


def test_streaming_service_uses_thread_runtime_epilogue_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.epilogue")
    execution_source = inspect.getsource(importlib.import_module("backend.thread_runtime.run.execution"))

    assert owner_module.emit_run_epilogue is not None
    assert "from backend.thread_runtime.run import epilogue as _run_epilogue" in execution_source


def test_streaming_service_uses_thread_runtime_execution_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.execution")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))

    assert owner_module.run_agent_to_buffer is not None
    assert "from backend.thread_runtime.run import execution as _run_execution" in streaming_source


def test_lifespan_uses_neutral_display_builder_owner() -> None:
    owner_module = importlib.import_module("backend.display_builder")
    lifespan_source = inspect.getsource(importlib.import_module("backend.web.core.lifespan"))

    assert owner_module.DisplayBuilder is not None
    assert "from backend.web.services.display_builder import DisplayBuilder" not in lifespan_source
    assert "from backend.display_builder import DisplayBuilder" in lifespan_source
