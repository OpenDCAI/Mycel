from __future__ import annotations

import importlib


def test_thread_runtime_namespace_exports_binding_and_state_helpers() -> None:
    binding_owner = importlib.import_module("backend.thread_runtime.binding")
    binding_shell = importlib.import_module("backend.web.services.thread_runtime_binding_service")
    state_owner = importlib.import_module("backend.thread_runtime.state")
    state_shell = importlib.import_module("backend.web.services.thread_state_service")

    assert binding_owner.resolve_thread_runtime_binding is binding_shell.resolve_thread_runtime_binding
    assert binding_owner.ThreadRuntimeBindingError is binding_shell.ThreadRuntimeBindingError
    assert state_owner.get_sandbox_info is state_shell.get_sandbox_info
    assert state_owner.get_sandbox_status_from_repos is state_shell.get_sandbox_status_from_repos
