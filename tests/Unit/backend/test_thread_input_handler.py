import asyncio
from types import SimpleNamespace

import pytest

from backend.threads.chat_adapters.thread_handler import NativeAgentThreadInputHandler
from core.runtime.middleware.monitor import AgentState
from protocols.agent_runtime import AgentRuntimeActor, AgentRuntimeMessage, AgentThreadInputEnvelope, AgentThreadInputResult


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
        get_or_create_agent=lambda *_args, **_kwargs: None,
        resolve_thread_sandbox=lambda *_args, **_kwargs: "local",
        start_agent_run=lambda *_args, **_kwargs: "run-123",
        clear_resource_overview_cache=lambda: None,
    )

    assert handler._queue_manager is injected_queue_manager
    assert handler._thread_tasks is injected_thread_tasks
    assert handler._thread_locks is injected_thread_locks
    assert handler._thread_locks_guard is injected_thread_locks_guard


@pytest.mark.asyncio
async def test_thread_input_handler_uses_injected_runtime_callables():
    calls: list[tuple[str, object]] = []
    thread_tasks: dict[str, object] = {}
    thread_locks: dict[str, asyncio.Lock] = {}
    thread_locks_guard = asyncio.Lock()

    class _QueueManager:
        def enqueue(self, *_args, **_kwargs):
            raise AssertionError("enqueue should not be used for idle -> active routing")

    class _Runtime:
        def __init__(self) -> None:
            self.current_state = AgentState.IDLE

        def transition(self, next_state: AgentState) -> bool:
            self.current_state = next_state
            return True

    agent = SimpleNamespace(runtime=_Runtime())

    async def _get_or_create_agent(app, sandbox_type: str, *, thread_id: str):
        calls.append(("get_or_create_agent", (app, sandbox_type, thread_id)))
        return agent

    def _resolve_thread_sandbox(app, thread_id: str):
        calls.append(("resolve_thread_sandbox", (app, thread_id)))
        return "local"

    def _start_agent_run(agent_obj, thread_id: str, content: str, app, **kwargs):
        calls.append(("start_agent_run", (agent_obj, thread_id, content, app, kwargs["enable_trajectory"])))
        return "run-123"

    def _clear_resource_overview_cache():
        calls.append(("clear_cache", None))

    app = SimpleNamespace(state=SimpleNamespace())
    handler = NativeAgentThreadInputHandler(
        app,
        queue_manager=_QueueManager(),
        thread_tasks=thread_tasks,
        thread_locks=thread_locks,
        thread_locks_guard=thread_locks_guard,
        get_or_create_agent=_get_or_create_agent,
        resolve_thread_sandbox=_resolve_thread_sandbox,
        start_agent_run=_start_agent_run,
        clear_resource_overview_cache=_clear_resource_overview_cache,
    )

    result = await handler.dispatch(
        AgentThreadInputEnvelope(
            thread_id="thread-1",
            sender=AgentRuntimeActor(user_id="owner-1", user_type="human", display_name="Owner", source="owner"),
            message=AgentRuntimeMessage(content="hello"),
        )
    )

    assert result == AgentThreadInputResult(status="started", routing="direct", run_id="run-123", thread_id="thread-1")
    assert calls == [
        ("resolve_thread_sandbox", (app, "thread-1")),
        ("get_or_create_agent", (app, "local", "thread-1")),
        ("start_agent_run", (agent, "thread-1", "hello", app, False)),
        ("clear_cache", None),
    ]
