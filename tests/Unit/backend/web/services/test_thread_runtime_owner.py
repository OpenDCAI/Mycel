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
