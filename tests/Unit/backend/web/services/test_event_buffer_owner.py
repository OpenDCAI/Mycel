from __future__ import annotations

import importlib


def test_thread_runtime_namespace_exports_legacy_helpers() -> None:
    history_owner = importlib.import_module("backend.thread_runtime.history")
    history_shell = importlib.import_module("backend.thread_history")
    projection_owner = importlib.import_module("backend.thread_runtime.projection")
    projection_shell = importlib.import_module("backend.thread_projection")
    convergence_owner = importlib.import_module("backend.thread_runtime.convergence")
    sandbox_owner = importlib.import_module("backend.thread_runtime.sandbox")
    reads_owner = importlib.import_module("backend.thread_runtime.events.reads")
    buffer_owner = importlib.import_module("backend.thread_runtime.events.buffer")

    assert history_owner.build_thread_history_transport is history_shell.build_thread_history_transport
    assert projection_owner.canonical_owner_threads is projection_shell.canonical_owner_threads
    assert convergence_owner.inspect_owner_thread_runtime is not None
    assert sandbox_owner.resolve_thread_sandbox is not None
    assert reads_owner.build_run_event_read_transport is not None
    assert buffer_owner.ThreadEventBuffer is not None
    assert buffer_owner.RunEventBuffer is not None
