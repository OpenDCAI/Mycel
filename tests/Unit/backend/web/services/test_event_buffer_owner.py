from __future__ import annotations

import importlib

import pytest


def test_thread_runtime_namespace_exports_legacy_helpers() -> None:
    history_owner = importlib.import_module("backend.threads.history")
    projection_owner = importlib.import_module("backend.threads.projection")
    convergence_owner = importlib.import_module("backend.threads.convergence")
    sandbox_owner = importlib.import_module("backend.threads.sandbox_resolution")
    reads_owner = importlib.import_module("backend.threads.events.reads")
    buffer_owner = importlib.import_module("backend.threads.events.buffer")

    assert history_owner.build_thread_history_transport is not None
    assert projection_owner.canonical_owner_threads is not None
    assert convergence_owner.inspect_owner_thread_runtime is not None
    assert sandbox_owner.resolve_thread_sandbox is not None
    assert reads_owner.build_run_event_read_transport is not None
    assert buffer_owner.ThreadEventBuffer is not None
    assert buffer_owner.RunEventBuffer is not None


def test_thread_history_shell_is_deleted() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("backend.thread_history")


def test_thread_projection_shell_is_deleted() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("backend.thread_projection")
