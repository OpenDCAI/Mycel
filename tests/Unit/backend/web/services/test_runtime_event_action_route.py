from __future__ import annotations

import asyncio
from collections.abc import Iterable

import pytest

from backend.threads.chat_adapters.runtime_event_action_route import RuntimeEventActionRoute


@pytest.mark.asyncio
async def test_runtime_event_action_route_dispatches_planned_actions() -> None:
    calls: list[list[str]] = []

    def planner(value: str) -> list[str]:
        return [f"planned:{value}"]

    async def dispatch_actions(actions: Iterable[str]) -> str:
        calls.append(list(actions))
        return "sent"

    route = RuntimeEventActionRoute(planner=planner, dispatch_actions=dispatch_actions)

    result = await route.dispatch("event-1")

    assert result == "sent"
    assert calls == [["planned:event-1"]]


@pytest.mark.asyncio
async def test_runtime_event_action_route_does_not_materialize_planned_actions_before_dispatch() -> None:
    events: list[str] = []

    def planner(value: str) -> Iterable[str]:
        events.append("planner-start")
        yield f"planned:{value}"
        events.append("planner-after-first")
        yield "planned:late"

    async def dispatch_actions(actions: Iterable[str]) -> str:
        events.append("dispatch-start")
        iterator = iter(actions)
        events.append(next(iterator))
        return "sent"

    route = RuntimeEventActionRoute(planner=planner, dispatch_actions=dispatch_actions)

    result = await route.dispatch("event-1")

    assert result == "sent"
    assert events == ["dispatch-start", "planner-start", "planned:event-1"]


@pytest.mark.asyncio
async def test_runtime_event_action_route_sync_hook_runs_from_worker_thread() -> None:
    calls: list[list[str]] = []

    def planner(value: str) -> list[str]:
        return [f"planned:{value}"]

    async def dispatch_actions(actions: Iterable[str]) -> None:
        calls.append(list(actions))

    hook = RuntimeEventActionRoute(planner=planner, dispatch_actions=dispatch_actions).sync_hook()

    await asyncio.to_thread(hook, "event-1")

    assert calls == [["planned:event-1"]]


@pytest.mark.asyncio
async def test_runtime_event_action_route_sync_hook_fails_loudly_on_owner_loop_thread() -> None:
    def planner(value: str) -> list[str]:
        return [value]

    async def dispatch_actions(_actions: Iterable[str]) -> None:
        return None

    hook = RuntimeEventActionRoute(planner=planner, dispatch_actions=dispatch_actions).sync_hook()

    with pytest.raises(RuntimeError) as exc:
        hook("event-1")

    assert str(exc.value) == "Sync runtime event hook cannot run on its owner event loop thread"
