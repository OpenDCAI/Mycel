from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.threads.chat_adapters.bootstrap import build_agent_runtime_gateway
from core.runtime.middleware.monitor import AgentState
from protocols.agent_runtime import AgentRuntimeActor, AgentRuntimeMessage, AgentThreadInputEnvelope, AgentThreadInputResult


class _FakeQueueManager:
    def enqueue(self, *args, **kwargs) -> None:
        raise AssertionError("enqueue should not be used for idle -> active routing")


class _FakeRuntime:
    def __init__(self) -> None:
        self.current_state = AgentState.IDLE

    def transition(self, next_state: AgentState) -> bool:
        self.current_state = next_state
        return True


class _FakeAgent:
    def __init__(self) -> None:
        self.runtime = _FakeRuntime()


def _fake_app() -> SimpleNamespace:
    thread_repo = SimpleNamespace(
        get_by_id=lambda thread_id: {"id": thread_id, "sandbox_type": "local"},
        get_by_user_id=lambda _uid: None,
        list_by_agent_user=lambda _uid: [],
    )
    return SimpleNamespace(
        state=SimpleNamespace(
            threads_runtime_state=SimpleNamespace(thread_repo=thread_repo),
            agent_pool={},
            queue_manager=_FakeQueueManager(),
            thread_cwd={},
            thread_sandbox={},
            thread_locks={},
            thread_locks_guard=asyncio.Lock(),
            thread_tasks={},
        )
    )


def _thread_input(content: str = "hello", *, enable_trajectory: bool = False) -> AgentThreadInputEnvelope:
    return AgentThreadInputEnvelope(
        thread_id="thread-1",
        sender=AgentRuntimeActor(user_id="owner-1", user_type="human", display_name="Owner", source="owner"),
        message=AgentRuntimeMessage(content=content),
        enable_trajectory=enable_trajectory,
    )


@pytest.mark.asyncio
async def test_gateway_thread_input_clears_resource_overview_cache_when_starting_run() -> None:
    app = _fake_app()
    agent = _FakeAgent()
    typing_tracker = SimpleNamespace(start_chat=lambda *_args, **_kwargs: None)

    with (
        patch("backend.threads.chat_adapters.bootstrap.resolve_thread_sandbox", return_value="local"),
        patch("backend.threads.chat_adapters.bootstrap.get_or_create_agent", AsyncMock(return_value=agent)),
        patch("backend.threads.chat_adapters.bootstrap.start_agent_run", return_value="run-123"),
        patch("backend.threads.chat_adapters.bootstrap.clear_resource_overview_cache") as clear_cache,
    ):
        result = await build_agent_runtime_gateway(
            app,
            thread_repo=app.state.threads_runtime_state.thread_repo,
            typing_tracker=typing_tracker,
        ).dispatch_thread_input(_thread_input())

    assert result == AgentThreadInputResult(status="started", routing="direct", run_id="run-123", thread_id="thread-1")
    clear_cache.assert_called_once_with()


@pytest.mark.asyncio
async def test_gateway_thread_input_requires_agent_runtime() -> None:
    app = _fake_app()
    typing_tracker = SimpleNamespace(start_chat=lambda *_args, **_kwargs: None)

    with (
        patch("backend.threads.chat_adapters.bootstrap.resolve_thread_sandbox", return_value="local"),
        patch("backend.threads.chat_adapters.bootstrap.get_or_create_agent", AsyncMock(return_value=SimpleNamespace())),
        patch("backend.threads.chat_adapters.bootstrap.start_agent_run", return_value="run-123"),
        patch("backend.threads.chat_adapters.bootstrap.clear_resource_overview_cache"),
    ):
        with pytest.raises(AttributeError):
            await build_agent_runtime_gateway(
                app,
                thread_repo=app.state.threads_runtime_state.thread_repo,
                typing_tracker=typing_tracker,
            ).dispatch_thread_input(_thread_input())


@pytest.mark.asyncio
async def test_gateway_thread_input_passes_enable_trajectory_to_start_agent_run() -> None:
    app = _fake_app()
    agent = _FakeAgent()
    typing_tracker = SimpleNamespace(start_chat=lambda *_args, **_kwargs: None)

    with (
        patch("backend.threads.chat_adapters.bootstrap.resolve_thread_sandbox", return_value="local"),
        patch("backend.threads.chat_adapters.bootstrap.get_or_create_agent", AsyncMock(return_value=agent)),
        patch("backend.threads.chat_adapters.bootstrap.start_agent_run", return_value="run-123") as start_run,
        patch("backend.threads.chat_adapters.bootstrap.clear_resource_overview_cache"),
    ):
        await build_agent_runtime_gateway(
            app,
            thread_repo=app.state.threads_runtime_state.thread_repo,
            typing_tracker=typing_tracker,
        ).dispatch_thread_input(_thread_input(enable_trajectory=True))

    assert start_run.call_args.kwargs["enable_trajectory"] is True
