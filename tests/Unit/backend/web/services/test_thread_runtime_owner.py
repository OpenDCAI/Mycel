from __future__ import annotations

import importlib
import inspect


def test_thread_runtime_namespace_exports_binding_and_state_helpers() -> None:
    binding_owner = importlib.import_module("backend.thread_runtime.binding")
    binding_shell = importlib.import_module("backend.web.services.thread_runtime_binding_service")
    state_owner = importlib.import_module("backend.thread_runtime.state")
    state_shell = importlib.import_module("backend.web.services.thread_state_service")

    assert binding_owner.resolve_thread_runtime_binding is binding_shell.resolve_thread_runtime_binding
    assert binding_owner.ThreadRuntimeBindingError is binding_shell.ThreadRuntimeBindingError
    assert state_owner.get_sandbox_info is state_shell.get_sandbox_info
    assert state_owner.get_sandbox_status_from_repos is state_shell.get_sandbox_status_from_repos


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
    shell_module = importlib.import_module("backend.web.services.thread_message_interruption_service")

    assert owner_module.repair_interrupted_tool_call_messages is shell_module.repair_interrupted_tool_call_messages
    assert "from backend.thread_runtime.interruption import repair_interrupted_tool_call_messages" in history_source
    assert "backend.web.services.thread_message_interruption_service" not in history_source


def test_thread_runtime_namespace_exports_owner_thread_reads() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.owner_reads")
    shell_module = importlib.import_module("backend.web.services.owner_thread_read_service")

    assert owner_module.list_owner_thread_rows_for_auth_burst is shell_module.list_owner_thread_rows_for_auth_burst


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

    assert hasattr(agent_pool_module, "get_or_create_agent")
    assert hasattr(agent_pool_module, "update_agent_config")
    assert "from backend.thread_runtime.pool import registry as _registry" in source
    assert "async def get_or_create_agent(" in source
    assert "async def update_agent_config(" in source
    assert hasattr(agent_pool_module, "get_or_create_agent_id")
    assert hasattr(agent_pool_module, "get_file_channel_binding")
    assert owner_module.get_or_create_agent.__module__ == "backend.thread_runtime.pool.registry"
    assert owner_module.update_agent_config.__module__ == "backend.thread_runtime.pool.registry"


def test_thread_launch_config_uses_thread_runtime_launch_config_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.launch_config")
    shell_module = importlib.import_module("backend.web.services.thread_launch_config_service")

    assert owner_module.normalize_launch_config_payload is not None
    assert hasattr(shell_module, "normalize_launch_config_payload")
    assert hasattr(shell_module, "build_new_launch_config")
    assert hasattr(shell_module, "resolve_default_config")


def test_thread_runtime_pool_exports_idle_reaper_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.pool.idle_reaper")
    shell_module = importlib.import_module("backend.web.services.idle_reaper")

    assert hasattr(shell_module, "run_idle_reaper_once")
    assert hasattr(shell_module, "idle_reaper_loop")
    assert owner_module.__name__ == "backend.thread_runtime.pool.idle_reaper"


def test_thread_visibility_uses_thread_projection_owner() -> None:
    owner_module = importlib.import_module("backend.thread_projection")
    shell_module = importlib.import_module("backend.web.services.thread_visibility")

    assert owner_module.canonical_owner_threads is shell_module.canonical_owner_threads


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

    assert owner_module.get_or_create_thread_buffer is not None
    assert owner_module.ensure_thread_handlers is not None
    assert "from backend.thread_runtime.run import buffer_wiring as _run_buffer_wiring" in streaming_source


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

    assert owner_module.observe_thread_events is not None
    assert owner_module.observe_run_events is not None
    assert owner_module.observe_sse_buffer is not None
    assert "from backend.thread_runtime.run import observer as _run_observer" in streaming_source


def test_streaming_service_uses_thread_runtime_trajectory_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.trajectory")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))

    assert owner_module.build_trajectory_scope is not None
    assert "from backend.thread_runtime.run import trajectory as _run_trajectory" in streaming_source


def test_streaming_service_uses_thread_runtime_observation_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.observation")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))

    assert owner_module.build_observation is not None
    assert "from backend.thread_runtime.run import observation as _run_observation" in streaming_source


def test_streaming_service_uses_thread_runtime_activity_bridge_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.activity_bridge")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))

    assert owner_module.build_activity_bridge is not None
    assert "from backend.thread_runtime.run import activity_bridge as _run_activity_bridge" in streaming_source


def test_streaming_service_uses_thread_runtime_emit_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.emit")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))

    assert owner_module.build_emit is not None
    assert "from backend.thread_runtime.run import emit as _run_emit" in streaming_source


def test_streaming_service_uses_thread_runtime_prologue_owner() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.run.prologue")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))

    assert owner_module.emit_run_prologue is not None
    assert "from backend.thread_runtime.run import prologue as _run_prologue" in streaming_source
