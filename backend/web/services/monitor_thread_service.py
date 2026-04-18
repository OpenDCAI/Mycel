"""Thread read boundary for Monitor."""

from __future__ import annotations

from typing import Any

from backend.web.services.resource_common import thread_owners as _thread_owners
from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo


def list_monitor_threads(app: Any, user_id: str) -> dict[str, Any]:
    from backend.web.routers.threads import build_owner_thread_workbench

    return build_owner_thread_workbench(app, user_id)


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


async def get_monitor_thread_detail(app: Any, thread_id: str) -> dict[str, Any]:
    from backend.web.services.monitor_trace_service import build_monitor_thread_trajectory

    thread_repo = getattr(app.state, "thread_repo", None)
    if thread_repo is None:
        raise RuntimeError("thread_repo is required for monitor thread detail")

    thread = thread_repo.get_by_id(thread_id)
    if thread is None:
        raise KeyError(f"Thread not found: {thread_id}")

    repo = make_sandbox_monitor_repo()
    try:
        summary = repo.query_thread_summary(thread_id)
        runtime_rows = repo.query_thread_runtime_rows(thread_id)
    finally:
        repo.close()

    if summary is None:
        summary = _derive_thread_summary_from_runtime_rows(runtime_rows)
    summary = _normalize_thread_summary(summary)

    owners = _thread_owners(
        [thread_id],
        user_repo=getattr(app.state, "user_repo", None),
        thread_repo=thread_repo,
    )

    return {
        "thread": _normalize_monitor_thread(thread, thread_id),
        "owner": _normalize_thread_owner(owners.get(thread_id)),
        "summary": summary,
        "sessions": runtime_rows,
        "trajectory": await build_monitor_thread_trajectory(app, thread_id),
    }
