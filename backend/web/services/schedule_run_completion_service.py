"""Schedule run finalization from real runtime boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from backend.web.services import schedule_service

TerminalScheduleStatus = Literal["succeeded", "failed", "cancelled"]


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def complete_schedule_run_from_runtime(
    schedule_run_id: str | None,
    *,
    source: str | None,
    status: TerminalScheduleStatus,
    runtime_run_id: str,
    thread_id: str,
    error: str | None = None,
) -> None:
    if not schedule_run_id:
        if source == "schedule":
            raise RuntimeError("schedule source runtime run is missing schedule_run_id metadata")
        return

    existing = schedule_service.get_schedule_run(schedule_run_id)
    if existing is None:
        raise RuntimeError(f"schedule run {schedule_run_id} not found")
    output_json = dict(existing.get("output_json") or {})
    output_json["runtime"] = {
        "run_id": runtime_run_id,
        "thread_id": thread_id,
        "status": status,
    }
    schedule_service.update_schedule_run(
        schedule_run_id,
        status=status,
        completed_at=_now_iso(),
        output_json=output_json,
        error=error,
    )
