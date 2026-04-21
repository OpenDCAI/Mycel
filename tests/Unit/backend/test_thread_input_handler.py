import asyncio
from types import SimpleNamespace

from backend.threads.chat_adapters.thread_handler import NativeAgentThreadInputHandler


def test_thread_input_handler_uses_injected_runtime_state():
    injected_queue_manager = object()
    injected_thread_tasks = {}
    injected_thread_locks = {}
    injected_thread_locks_guard = asyncio.Lock()

    app = SimpleNamespace(
        state=SimpleNamespace(
            queue_manager=object(),
            thread_tasks={"wrong": object()},
            thread_locks={"wrong": object()},
            thread_locks_guard=object(),
        )
    )

    handler = NativeAgentThreadInputHandler(
        app,
        queue_manager=injected_queue_manager,
        thread_tasks=injected_thread_tasks,
        thread_locks=injected_thread_locks,
        thread_locks_guard=injected_thread_locks_guard,
    )

    assert handler._queue_manager is injected_queue_manager
    assert handler._thread_tasks is injected_thread_tasks
    assert handler._thread_locks is injected_thread_locks
    assert handler._thread_locks_guard is injected_thread_locks_guard
