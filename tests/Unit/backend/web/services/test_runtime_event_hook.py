from __future__ import annotations

import asyncio

import pytest

from backend.threads.chat_adapters.runtime_event_hook import (
    make_sync_planned_runtime_event_hook,
    make_sync_runtime_event_hook,
    run_planned_runtime_event,
)


@pytest.mark.asyncio
async def test_sync_runtime_event_hook_runs_coroutine_from_worker_thread() -> None:
    calls: list[str] = []

    async def record(value: str) -> None:
        calls.append(value)

    hook = make_sync_runtime_event_hook(record)

    await asyncio.to_thread(hook, "ok")

    assert calls == ["ok"]


@pytest.mark.asyncio
async def test_sync_runtime_event_hook_fails_loudly_on_owner_loop_thread() -> None:
    async def noop() -> None:
        return None

    hook = make_sync_runtime_event_hook(noop)

    with pytest.raises(RuntimeError) as exc:
        hook()

    assert str(exc.value) == "Sync runtime event hook cannot run on its owner event loop thread"


@pytest.mark.parametrize(
    ("planned_actions", "expected_count"),
    [
        (["planned:event-1"], 1),
        ([], 0),
    ],
)
@pytest.mark.asyncio
async def test_run_planned_runtime_event_dispatches_planned_actions(
    planned_actions: list[str],
    expected_count: int,
) -> None:
    calls: list[list[str]] = []

    def planner(_value: str) -> list[str]:
        return planned_actions

    async def dispatch(actions: list[str]) -> None:
        calls.append(actions)

    action_count = await run_planned_runtime_event("event-1", planner, dispatch)

    assert action_count == expected_count
    assert calls == [planned_actions]


@pytest.mark.asyncio
async def test_sync_planned_runtime_event_hook_plans_and_dispatches_actions_from_worker_thread() -> None:
    calls: list[list[str]] = []

    def planner(value: str) -> list[str]:
        return [f"planned:{value}"]

    async def dispatch(actions: list[str]) -> None:
        calls.append(actions)

    hook = make_sync_planned_runtime_event_hook(planner, dispatch)

    await asyncio.to_thread(hook, "event-1")

    assert calls == [["planned:event-1"]]
