from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


def _decode(events: list[dict[str, str]]) -> list[tuple[str, dict[str, object]]]:
    return [(event["event"], json.loads(event["data"])) for event in events]


@pytest.mark.asyncio
async def test_emit_run_prologue_owner_message_emits_user_message_then_run_start() -> None:
    from backend.thread_runtime.run.prologue import emit_run_prologue

    events: list[dict[str, str]] = []

    async def emit(event: dict[str, str]) -> None:
        events.append(event)

    app = SimpleNamespace(state=SimpleNamespace(thread_last_active={}))
    runtime = SimpleNamespace(current_run_source=None)
    agent = SimpleNamespace(runtime=runtime)

    await emit_run_prologue(
        agent=agent,
        thread_id="thread-1",
        message="<system-reminder>ignore</system-reminder>hello",
        message_metadata=None,
        run_id="run-1",
        app=app,
        emit=emit,
    )

    decoded = _decode(events)
    assert [item[0] for item in decoded] == ["user_message", "run_start"]
    assert decoded[0][1] == {"content": "hello", "showing": True}
    assert decoded[1][1]["run_id"] == "run-1"
    assert decoded[1][1]["thread_id"] == "thread-1"
    assert runtime.current_run_source == "owner"
    assert "thread-1" in app.state.thread_last_active


@pytest.mark.asyncio
async def test_emit_run_prologue_skips_duplicate_user_message_for_steer() -> None:
    from backend.thread_runtime.run.prologue import emit_run_prologue

    events: list[dict[str, str]] = []

    async def emit(event: dict[str, str]) -> None:
        events.append(event)

    app = SimpleNamespace(state=SimpleNamespace(thread_last_active={}))
    runtime = SimpleNamespace(current_run_source=None)
    agent = SimpleNamespace(runtime=runtime)

    await emit_run_prologue(
        agent=agent,
        thread_id="thread-steer",
        message="steer please",
        message_metadata={"notification_type": "steer"},
        run_id="run-steer",
        app=app,
        emit=emit,
    )

    decoded = _decode(events)
    assert [item[0] for item in decoded] == ["run_start"]
    assert decoded[0][1]["source"] is None


@pytest.mark.asyncio
async def test_emit_run_prologue_emits_notice_after_run_start_for_system_message() -> None:
    from backend.thread_runtime.run.prologue import emit_run_prologue

    events: list[dict[str, str]] = []

    async def emit(event: dict[str, str]) -> None:
        events.append(event)

    app = SimpleNamespace(state=SimpleNamespace(thread_last_active={}))
    runtime = SimpleNamespace(current_run_source=None)
    agent = SimpleNamespace(runtime=runtime)

    await emit_run_prologue(
        agent=agent,
        thread_id="thread-system",
        message="system notice",
        message_metadata={"source": "system", "notification_type": "agent"},
        run_id="run-system",
        app=app,
        emit=emit,
    )

    decoded = _decode(events)
    assert [item[0] for item in decoded] == ["run_start", "notice"]
    assert decoded[1][1] == {
        "content": "system notice",
        "source": "system",
        "notification_type": "agent",
    }
