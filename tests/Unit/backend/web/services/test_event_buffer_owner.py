from __future__ import annotations

import importlib
import inspect


def test_event_buffer_owner_lives_under_backend_thread_runtime() -> None:
    owner_module = importlib.import_module("backend.thread_runtime.event_buffer")
    shell_module = importlib.import_module("backend.web.services.event_buffer")
    streaming_source = inspect.getsource(importlib.import_module("backend.web.services.streaming_service"))
    threads_source = inspect.getsource(importlib.import_module("backend.web.routers.threads"))

    assert owner_module.ThreadEventBuffer is shell_module.ThreadEventBuffer
    assert owner_module.RunEventBuffer is shell_module.RunEventBuffer
    assert owner_module.__name__ == "backend.thread_runtime.event_buffer"
    assert "backend.thread_runtime.event_buffer" in streaming_source
    assert "backend.thread_runtime.event_buffer" in threads_source
    assert "backend.web.services.event_buffer" not in streaming_source
