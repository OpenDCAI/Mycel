from __future__ import annotations

import pytest

from backend.threads.chat_adapters.runtime_event_runner import run_planned_runtime_event


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
