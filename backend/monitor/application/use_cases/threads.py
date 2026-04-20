"""Thread read boundary for Monitor."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.monitor.application.use_cases import thread_workbench
from backend.monitor.application.use_cases import trace as monitor_trace
from backend.monitor.infrastructure.read_models import sandbox_read_service
from backend.monitor.infrastructure.read_models.thread_workbench_read_service import OwnerThreadWorkbenchReader
from backend.monitor.infrastructure.read_models.trace_read_service import MonitorTraceReader


def list_monitor_threads(user_id: str, *, workbench_reader: OwnerThreadWorkbenchReader) -> dict[str, object]:
    return thread_workbench.build_owner_thread_workbench(user_id, reader=workbench_reader)


def _derive_thread_summary_from_runtime_rows(runtime_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not runtime_rows:
        return None
    latest = runtime_rows[0]
    summary = {
        "sandbox_id": latest.get("sandbox_id"),
        "provider_name": latest.get("provider_name"),
        "current_instance_id": latest.get("current_instance_id"),
        "desired_state": latest.get("desired_state"),
        "observed_state": latest.get("observed_state"),
    }
    return summary if any(value is not None for value in summary.values()) else None


def _normalize_thread_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    payload = {
        "sandbox_id": summary.get("sandbox_id"),
        "provider_name": summary.get("provider_name"),
        "current_instance_id": summary.get("current_instance_id"),
        "desired_state": summary.get("desired_state"),
        "observed_state": summary.get("observed_state"),
    }
    return payload if any(value is not None for value in payload.values()) else None


def _normalize_thread_owner(owner: dict[str, Any] | None) -> dict[str, Any] | None:
    if owner is None:
        return None
    return {
        "user_id": owner.get("user_id") or owner.get("agent_user_id"),
        "display_name": owner.get("display_name") or owner.get("agent_name"),
        "email": owner.get("email"),
        "avatar_url": owner.get("avatar_url"),
    }


def _normalize_monitor_thread(thread: dict[str, Any], requested_thread_id: str) -> dict[str, Any]:
    return {
        **thread,
        "thread_id": thread.get("thread_id") or thread.get("id") or requested_thread_id,
    }


async def get_monitor_thread_detail(
    thread_id: str,
    *,
    load_thread_base: Callable[[str], dict[str, Any]],
    trace_reader: MonitorTraceReader,
) -> dict[str, Any]:
    thread_base = load_thread_base(thread_id)
    rows = sandbox_read_service.load_thread_detail_rows(thread_id)
    summary = rows["summary"]
    runtime_rows = rows["runtime_rows"]

    if summary is None:
        summary = _derive_thread_summary_from_runtime_rows(runtime_rows)
    summary = _normalize_thread_summary(summary)

    return {
        "thread": _normalize_monitor_thread(thread_base["thread"], thread_id),
        "owner": _normalize_thread_owner(thread_base["owner"]),
        "summary": summary,
        "runtime_rows": runtime_rows,
        "trajectory": await monitor_trace.build_monitor_thread_trajectory(thread_id, trace_reader=trace_reader),
    }
