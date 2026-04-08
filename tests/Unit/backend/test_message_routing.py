from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.web.services.message_routing import route_message_to_brain
from core.runtime.middleware.monitor import AgentState


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


@pytest.mark.asyncio
async def test_route_message_to_brain_clears_resource_overview_cache_when_starting_run() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            queue_manager=_FakeQueueManager(),
            thread_locks={},
            thread_locks_guard=asyncio.Lock(),
        )
    )
    agent = _FakeAgent()

    with (
        patch("backend.web.services.agent_pool.resolve_thread_sandbox", return_value="local"),
        patch("backend.web.services.agent_pool.get_or_create_agent", AsyncMock(return_value=agent)),
        patch("backend.web.services.streaming_service.start_agent_run", return_value="run-123"),
        patch("backend.web.services.resource_cache.clear_monitor_resource_overview_cache") as clear_cache,
    ):
        result = await route_message_to_brain(app, "thread-1", "hello")

    assert result == {"status": "started", "routing": "direct", "run_id": "run-123", "thread_id": "thread-1"}
    clear_cache.assert_called_once_with()


@pytest.mark.asyncio
async def test_route_message_to_brain_passes_enable_trajectory_to_start_agent_run() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            queue_manager=_FakeQueueManager(),
            thread_locks={},
            thread_locks_guard=asyncio.Lock(),
        )
    )
    agent = _FakeAgent()

    with (
        patch("backend.web.services.agent_pool.resolve_thread_sandbox", return_value="local"),
        patch("backend.web.services.agent_pool.get_or_create_agent", AsyncMock(return_value=agent)),
        patch("backend.web.services.streaming_service.start_agent_run", return_value="run-123") as start_run,
        patch("backend.web.services.resource_cache.clear_monitor_resource_overview_cache"),
    ):
        await route_message_to_brain(app, "thread-1", "hello", enable_trajectory=True)

    assert start_run.call_args.kwargs["enable_trajectory"] is True
