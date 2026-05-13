from __future__ import annotations

import asyncio

import pytest

from backend.threads.chat_adapters.runtime_event_action_route import RuntimeEventActionRoute


@pytest.mark.asyncio
async def test_runtime_event_action_route_dispatches_planned_actions() -> None:
    calls: list[list[str]] = []

    def planner(value: str) -> list[str]:
        return [f"planned:{value}"]

    async def dispatch_actions(actions: list[str]) -> str:
        calls.append(actions)
        return "sent"

    route = RuntimeEventActionRoute(planner=planner, dispatch_actions=dispatch_actions)

    result = await route.dispatch("event-1")

    assert result == "sent"
    assert calls == [["planned:event-1"]]


@pytest.mark.asyncio
async def test_runtime_event_action_route_sync_hook_runs_from_worker_thread() -> None:
    calls: list[list[str]] = []

    def planner(value: str) -> list[str]:
        return [f"planned:{value}"]

    async def dispatch_actions(actions: list[str]) -> None:
        calls.append(actions)

    hook = RuntimeEventActionRoute(planner=planner, dispatch_actions=dispatch_actions).sync_hook()

    await asyncio.to_thread(hook, "event-1")

    assert calls == [["planned:event-1"]]


@pytest.mark.asyncio
async def test_runtime_event_action_route_sync_hook_fails_loudly_on_owner_loop_thread() -> None:
    def planner(value: str) -> list[str]:
        return [value]

    async def dispatch_actions(_actions: list[str]) -> None:
        return None

    hook = RuntimeEventActionRoute(planner=planner, dispatch_actions=dispatch_actions).sync_hook()

    with pytest.raises(RuntimeError) as exc:
        hook("event-1")

    assert str(exc.value) == "Sync runtime event hook cannot run on its owner event loop thread"
