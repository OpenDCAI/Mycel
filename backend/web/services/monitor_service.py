"""Monitor service: sandbox observation + health diagnostics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.web.services import (
    monitor_evaluation_service,
    monitor_provider_runtime_service,
    monitor_sandbox_config_service,
    monitor_sandbox_detail_service,
    monitor_sandbox_projection_service,
    monitor_thread_service,
)


# ---------------------------------------------------------------------------
# Mapping helpers (private)
# ---------------------------------------------------------------------------
def list_monitor_threads(app: Any, user_id: str) -> dict[str, Any]:
    return monitor_thread_service.list_monitor_threads(app, user_id)


def get_monitor_sandbox_configs() -> dict[str, Any]:
    return monitor_sandbox_config_service.get_monitor_sandbox_configs()


def get_resource_overview_snapshot() -> dict[str, Any]:
    from backend.web.services.resource_cache import get_resource_overview_snapshot as _get_resource_overview_snapshot

    return _get_resource_overview_snapshot()


def _format_time_ago(iso_timestamp: str | None) -> str:
    dt = _parse_local_timestamp(iso_timestamp)
    if dt is None:
        return "never"
    delta = datetime.now() - dt
    if delta.days > 0:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    minutes = (delta.seconds % 3600) // 60
    if minutes > 0:
        return f"{minutes}m ago"
    return "just now"


def _make_badge(desired: str | None, observed: str | None) -> dict[str, Any]:
    if not desired and not observed:
        return {"desired": None, "observed": None, "converged": True, "color": "green", "text": "destroyed"}
    if desired == observed:
        return {"desired": desired, "observed": observed, "converged": True, "color": "green", "text": observed}
    return {
        "desired": desired,
        "observed": observed,
        "converged": False,
        "color": "yellow",
        "text": f"{observed} -> {desired}",
    }


def _thread_ref(thread_id: str | None) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "is_orphan": not thread_id,
    }


def _live_thread_ids(thread_ids: list[str]) -> set[str]:
    unique = sorted({str(thread_id or "").strip() for thread_id in thread_ids if str(thread_id or "").strip()})
    if not unique:
        return set()
    # @@@monitor-live-thread-state - monitor triage must validate terminal pointers against live
    # thread rows, otherwise stale abstract_terminals residue gets misclassified as healthy.
    owners = monitor_thread_service._thread_owners(unique)
    return {thread_id for thread_id in unique if (owners.get(thread_id) or {}).get("agent_user_id")}


SANDBOX_SEMANTIC_ORDER = [
    "orphan_diverged",
    "diverged",
    "orphan",
    "healthy",
]

SANDBOX_SEMANTIC_META = {
    "orphan_diverged": {
        "title": "Orphaned + Diverged",
        "description": "Sandbox lost thread binding while desired and observed state still disagree.",
    },
    "diverged": {
        "title": "Diverged",
        "description": "Sandbox is still attached to a thread, but runtime state has not converged.",
    },
    "orphan": {
        "title": "Orphans",
        "description": "Sandbox has no active thread binding. Usually cleanup or historical residue.",
    },
    "healthy": {
        "title": "Healthy",
        "description": "Sandbox has a thread binding and desired state matches observed state.",
    },
}


SANDBOX_TRIAGE_ORDER = [
    "active_drift",
    "detached_residue",
    "orphan_cleanup",
    "healthy_capacity",
]

SANDBOX_TRIAGE_META = {
    "active_drift": {
        "title": "Active Drift",
        "description": "Sandboxes whose desired and observed state still disagree recently enough to warrant attention.",
        "tone": "warning",
    },
    "detached_residue": {
        "title": "Detached Residue",
        "description": (
            "Sandboxes still marked desired=running but observed=detached long after the runtime "
            "stopped moving. Usually cleanup debt, not live pressure."
        ),
        "tone": "danger",
    },
    "orphan_cleanup": {
        "title": "Orphan Cleanup",
        "description": "Sandboxes that have already lost thread binding and mainly represent cleanup backlog or historical residue.",
        "tone": "warning",
    },
    "healthy_capacity": {
        "title": "Healthy Capacity",
        "description": "Sandboxes with attached thread context and converged runtime state.",
        "tone": "success",
    },
}

DETACHED_RESIDUE_THRESHOLD_HOURS = 4.0


def _classify_sandbox_semantics(*, thread_id: str | None, badge: dict[str, Any]) -> dict[str, str]:
    is_orphan = not bool(thread_id)
    is_converged = bool(badge.get("converged"))
    if is_orphan and not is_converged:
        category = "orphan_diverged"
    elif not is_converged:
        category = "diverged"
    elif is_orphan:
        category = "orphan"
    else:
        category = "healthy"
    meta = SANDBOX_SEMANTIC_META[category]
    return {
        "category": category,
        "title": meta["title"],
        "description": meta["description"],
    }


def _parse_local_timestamp(iso_timestamp: str | None) -> datetime | None:
    if not iso_timestamp:
        return None
    # @@@naive-local-time - SQLite timestamps in this module are local-time strings.
    cleaned = iso_timestamp
    if "Z" in cleaned:
        cleaned = cleaned.replace("Z", "")
    if "+" in cleaned:
        cleaned = cleaned.split("+")[0]
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _hours_since(iso_timestamp: str | None) -> float | None:
    dt = _parse_local_timestamp(iso_timestamp)
    if dt is None:
        return None
    delta = datetime.now() - dt
    return delta.total_seconds() / 3600


def _classify_sandbox_triage(
    *,
    thread_id: str | None,
    badge: dict[str, Any],
    observed_state: str | None,
    desired_state: str | None,
    updated_at: str | None,
) -> dict[str, Any]:
    observed = str(observed_state or "").strip().lower() or None
    desired = str(desired_state or "").strip().lower() or None
    age_hours = _hours_since(updated_at)
    is_orphan = not bool(thread_id)
    is_converged = bool(badge.get("converged"))

    if is_orphan:
        key = "orphan_cleanup"
    elif is_converged:
        key = "healthy_capacity"
    elif observed == "detached" and desired == "running" and age_hours is not None and age_hours >= DETACHED_RESIDUE_THRESHOLD_HOURS:
        key = "detached_residue"
    else:
        key = "active_drift"

    meta = SANDBOX_TRIAGE_META[key]
    return {
        "category": key,
        "title": meta["title"],
        "description": meta["description"],
        "tone": meta["tone"],
        "age_hours": age_hours,
    }


def _sandbox_groups(
    *,
    items: list[dict[str, Any]],
    order: list[str],
    meta_by_key: dict[str, dict[str, Any]],
    field: str,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    summary = {key: 0 for key in order}
    for item in items:
        summary[item[field]["category"]] += 1
    summary["total"] = len(items)

    groups = []
    for key in order:
        meta = meta_by_key[key]
        group_items = [item for item in items if item[field]["category"] == key]
        groups.append({"key": key, **meta, "count": len(group_items), "items": group_items})
    return summary, groups


def get_monitor_evaluation_workbench() -> dict[str, Any]:
    return monitor_evaluation_service.get_monitor_evaluation_workbench()


def get_monitor_evaluation_run_detail(run_id: str) -> dict[str, Any]:
    return monitor_evaluation_service.get_monitor_evaluation_run_detail(run_id)


def get_monitor_evaluation_batches(limit: int = 50) -> dict[str, Any]:
    return monitor_evaluation_service.get_monitor_evaluation_batches(limit=limit)


def get_monitor_evaluation_scenarios() -> dict[str, Any]:
    return monitor_evaluation_service.get_monitor_evaluation_scenarios()


def create_monitor_evaluation_batch(
    *,
    submitted_by_user_id: str,
    agent_user_id: str,
    scenario_ids: list[str],
    sandbox: str,
    max_concurrent: int,
) -> dict[str, Any]:
    return monitor_evaluation_service.create_monitor_evaluation_batch(
        submitted_by_user_id=submitted_by_user_id,
        agent_user_id=agent_user_id,
        scenario_ids=scenario_ids,
        sandbox=sandbox,
        max_concurrent=max_concurrent,
    )


def start_monitor_evaluation_batch(
    batch_id: str,
    *,
    base_url: str,
    token: str,
    schedule_task,
) -> dict[str, Any]:
    return monitor_evaluation_service.start_monitor_evaluation_batch(
        batch_id,
        base_url=base_url,
        token=token,
        schedule_task=schedule_task,
    )


def get_monitor_evaluation_batch_detail(batch_id: str) -> dict[str, Any]:
    return monitor_evaluation_service.get_monitor_evaluation_batch_detail(batch_id)


def _map_monitor_sandboxes(rows: list[dict[str, Any]], *, title: str) -> dict[str, Any]:
    live_threads = _live_thread_ids([str(row.get("thread_id") or "").strip() for row in rows])
    items = []
    for row in rows:
        thread_id = str(row.get("thread_id") or "").strip() or None
        if thread_id not in live_threads:
            thread_id = None
        badge = _make_badge(row["desired_state"], row["observed_state"])
        triage = _classify_sandbox_triage(
            thread_id=thread_id,
            badge=badge,
            observed_state=row["observed_state"],
            desired_state=row["desired_state"],
            updated_at=row["updated_at"],
        )
        item = {
            "sandbox_id": row.get("sandbox_id"),
            "provider": row["provider_name"],
            "instance_id": row["current_instance_id"],
            "thread": _thread_ref(thread_id),
            "state_badge": badge,
            "semantics": _classify_sandbox_semantics(thread_id=thread_id, badge=badge),
            "triage": triage,
            "error": row["last_error"],
            "updated_at": row["updated_at"],
            "updated_ago": _format_time_ago(row["updated_at"]),
        }
        items.append(item)

    summary, groups = _sandbox_groups(
        items=items,
        order=SANDBOX_SEMANTIC_ORDER,
        meta_by_key=SANDBOX_SEMANTIC_META,
        field="semantics",
    )
    triage_summary, triage_groups = _sandbox_groups(
        items=items,
        order=SANDBOX_TRIAGE_ORDER,
        meta_by_key=SANDBOX_TRIAGE_META,
        field="triage",
    )

    return {
        "source": "sandbox_canonical",
        "title": title,
        "count": len(items),
        "summary": summary,
        "groups": groups,
        "triage": {
            "summary": triage_summary,
            "groups": triage_groups,
        },
        "items": items,
    }


def list_monitor_sandboxes() -> dict[str, Any]:
    return monitor_sandbox_projection_service.list_monitor_sandboxes()


def list_monitor_provider_orphan_runtimes() -> dict[str, Any]:
    return monitor_provider_runtime_service.list_monitor_provider_orphan_runtimes()


def get_monitor_sandbox_detail(sandbox_id: str) -> dict[str, Any]:
    return monitor_sandbox_detail_service.get_monitor_sandbox_detail(sandbox_id)


def get_monitor_provider_detail(provider_id: str) -> dict[str, Any]:
    return monitor_provider_runtime_service.get_monitor_provider_detail(provider_id)


def get_monitor_runtime_detail(runtime_session_id: str) -> dict[str, Any]:
    return monitor_provider_runtime_service.get_monitor_runtime_detail(runtime_session_id)


async def get_monitor_thread_detail(app: Any, thread_id: str) -> dict[str, Any]:
    return await monitor_thread_service.get_monitor_thread_detail(app, thread_id)


def request_monitor_sandbox_cleanup(sandbox_id: str) -> dict[str, Any]:
    return monitor_sandbox_detail_service.request_monitor_sandbox_cleanup(sandbox_id)


def request_monitor_provider_orphan_runtime_cleanup(provider_name: str, runtime_id: str) -> dict[str, Any]:
    return monitor_provider_runtime_service.request_monitor_provider_orphan_runtime_cleanup(provider_name, runtime_id)


def get_monitor_operation_detail(operation_id: str) -> dict[str, Any]:
    return monitor_sandbox_detail_service.get_monitor_operation_detail(operation_id)


# ---------------------------------------------------------------------------
# Public API: diagnostics
# ---------------------------------------------------------------------------
