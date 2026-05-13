from __future__ import annotations

from types import SimpleNamespace

import pytest


class AIMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class ToolMessage:
    pass


@pytest.mark.asyncio
async def test_tool_call_dedup_prepopulates_checkpoint_ids_and_tracks_emission_state() -> None:
    from backend.threads.run.tool_call_dedup import ToolCallDedup

    agent = SimpleNamespace(
        agent=SimpleNamespace(
            aget_state=lambda _config: _fake_state(
                [
                    AIMessage([{"id": "tc-checkpoint-1"}, {"id": "tc-checkpoint-2"}]),
                    ToolMessage(),
                ]
            )
        )
    )

    dedup = ToolCallDedup()
    await dedup.prepopulate_from_checkpoint(agent, {"configurable": {"thread_id": "thread-1"}})

    assert dedup.is_duplicate("tc-checkpoint-1") is True
    assert dedup.is_duplicate("tc-checkpoint-2") is True
    assert dedup.already_emitted("tc-checkpoint-1") is True
    assert dedup.already_emitted("tc-new") is False

    dedup.register("tc-live")

    assert dedup.is_duplicate("tc-live") is False
    assert dedup.already_emitted("tc-live") is True


async def _fake_state(messages):
    return SimpleNamespace(values={"messages": messages})
