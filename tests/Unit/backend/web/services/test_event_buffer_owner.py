from __future__ import annotations

import importlib


def test_event_buffer_owner_lives_under_backend_thread_runtime() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.event_buffer")
    shell_module = importlib.import_module("backend.web.services.event_buffer")

    assert owner_module.ThreadEventBuffer is shell_module.ThreadEventBuffer
    assert owner_module.RunEventBuffer is shell_module.RunEventBuffer
    assert owner_module.__name__ == "backend.thread_runtime.event_buffer"
