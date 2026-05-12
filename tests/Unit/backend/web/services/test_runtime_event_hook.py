from __future__ import annotations

import asyncio

import pytest

from backend.threads.chat_adapters.runtime_event_hook import (
    make_planned_runtime_event_hook,
    make_sync_runtime_event_hook,
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
async def test_planned_runtime_event_hook_runs_planner_and_dispatcher_from_worker_thread() -> None:
    calls: list[list[str]] = []

    def planner(value: str) -> list[str]:
        return [f"planned:{value}"]

    async def dispatch_actions(actions: list[str]) -> None:
        calls.append(actions)

    hook = make_planned_runtime_event_hook(planner, dispatch_actions)

    await asyncio.to_thread(hook, "event-1")

    assert calls == [["planned:event-1"]]


@pytest.mark.asyncio
async def test_sync_runtime_event_hook_fails_loudly_on_owner_loop_thread() -> None:
    async def noop() -> None:
        return None

    hook = make_sync_runtime_event_hook(noop)

    with pytest.raises(RuntimeError) as exc:
        hook()

    assert str(exc.value) == "Sync runtime event hook cannot run on its owner event loop thread"
