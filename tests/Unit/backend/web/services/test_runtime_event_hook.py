from __future__ import annotations

import asyncio

import pytest

from backend.threads.chat_adapters.runtime_event_hook import (
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
    ("planned_actions", "dispatch_result"),
    [
        (["planned:event-1"], "sent"),
        ([], "nothing-to-send"),
    ],
)
@pytest.mark.asyncio
async def test_run_planned_runtime_event_returns_dispatch_result(
    planned_actions: list[str],
    dispatch_result: str,
) -> None:
    calls: list[list[str]] = []

    def planner(_value: str) -> list[str]:
        return planned_actions

    async def dispatch(actions: list[str]) -> str:
        calls.append(actions)
        return dispatch_result

    result = await run_planned_runtime_event("event-1", planner, dispatch)

    assert result == dispatch_result
    assert calls == [planned_actions]
