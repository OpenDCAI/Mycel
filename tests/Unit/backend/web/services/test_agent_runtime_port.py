from __future__ import annotations

from types import SimpleNamespace


def test_thread_input_transport_reads_transport_from_threads_runtime_state() -> None:
    from backend.threads.chat_adapters.port import get_thread_input_transport

    transport = object()
    app = SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(thread_input_transport=transport)))

    assert get_thread_input_transport(app) is transport
