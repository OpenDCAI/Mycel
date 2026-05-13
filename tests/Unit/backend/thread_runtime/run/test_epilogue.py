from __future__ import annotations

import json

import pytest


def _decode(events: list[dict[str, str]]) -> list[tuple[str, dict[str, object]]]:
    return [(event["event"], json.loads(event["data"])) for event in events]


@pytest.mark.asyncio
async def test_emit_run_epilogue_success_emits_status_then_run_done() -> None:
    from backend.threads.run.epilogue import emit_run_epilogue

    events: list[dict[str, str]] = []

    async def emit(event: dict[str, str]) -> None:
        events.append(event)

    await emit_run_epilogue(
        emit=emit,
        thread_id="thread-1",
        run_id="run-1",
        outcome="success",
        payload={"status": {"state": {"state": "idle", "flags": {}}, "calls": 0}},
    )

    assert _decode(events) == [
        ("status", {"state": {"state": "idle", "flags": {}}, "calls": 0}),
        ("run_done", {"thread_id": "thread-1", "run_id": "run-1"}),
    ]


@pytest.mark.asyncio
async def test_emit_run_epilogue_cancelled_emits_cancelled_then_run_done() -> None:
    from backend.threads.run.epilogue import emit_run_epilogue

    events: list[dict[str, str]] = []

    async def emit(event: dict[str, str]) -> None:
        events.append(event)

    await emit_run_epilogue(
        emit=emit,
        thread_id="thread-1",
        run_id="run-1",
        outcome="cancelled",
        payload={"cancelled_tool_call_ids": ["tc-1"]},
    )

    assert _decode(events) == [
        ("cancelled", {"message": "Run cancelled by user", "cancelled_tool_call_ids": ["tc-1"]}),
        ("run_done", {"thread_id": "thread-1", "run_id": "run-1"}),
    ]


@pytest.mark.asyncio
async def test_emit_run_epilogue_error_emits_error_then_run_done() -> None:
    from backend.threads.run.epilogue import emit_run_epilogue

    events: list[dict[str, str]] = []

    async def emit(event: dict[str, str]) -> None:
        events.append(event)

    await emit_run_epilogue(
        emit=emit,
        thread_id="thread-1",
        run_id="run-1",
        outcome="error",
        payload={"error": "boom"},
    )

    assert _decode(events) == [
        ("error", {"error": "boom"}),
        ("run_done", {"thread_id": "thread-1", "run_id": "run-1"}),
    ]
