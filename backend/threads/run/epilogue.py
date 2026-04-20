"""Run epilogue helpers for thread runtime runs."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable


async def emit_run_epilogue(
    *,
    emit: Callable[[dict[str, str]], Awaitable[None]],
    thread_id: str,
    run_id: str,
    outcome: str,
    payload: dict[str, object],
) -> None:
    if outcome == "success":
        await emit(
            {
                "event": "status",
                "data": json.dumps(payload["status"], ensure_ascii=False),
            }
        )
    elif outcome == "cancelled":
        await emit(
            {
                "event": "cancelled",
                "data": json.dumps(
                    {
                        "message": "Run cancelled by user",
                        "cancelled_tool_call_ids": payload["cancelled_tool_call_ids"],
                    }
                ),
            }
        )
    elif outcome == "error":
        await emit({"event": "error", "data": json.dumps({"error": payload["error"]}, ensure_ascii=False)})
    else:
        raise RuntimeError(f"unsupported run epilogue outcome: {outcome}")

    await emit({"event": "run_done", "data": json.dumps({"thread_id": thread_id, "run_id": run_id})})
