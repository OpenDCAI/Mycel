"""Monitor service: lease observation + health diagnostics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from eval.storage import TrajectoryStore
from storage.runtime import (
    build_sandbox_monitor_repo as make_sandbox_monitor_repo,
)


# ---------------------------------------------------------------------------
# Mapping helpers (private)
# ---------------------------------------------------------------------------
def make_eval_store() -> TrajectoryStore:
    return TrajectoryStore()


def _format_time_ago(iso_timestamp: str | None) -> str:
    if not iso_timestamp:
        return "never"
    # @@@naive-local-time - SQLite timestamps in this module are local-time strings.
    if "Z" in iso_timestamp:
        iso_timestamp = iso_timestamp.replace("Z", "")
    if "+" in iso_timestamp:
        iso_timestamp = iso_timestamp.split("+")[0]
    dt = datetime.fromisoformat(iso_timestamp)
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


LEASE_SEMANTIC_ORDER = [
    "orphan_diverged",
    "diverged",
    "orphan",
    "healthy",
]

LEASE_SEMANTIC_META = {
    "orphan_diverged": {
        "title": "Orphaned + Diverged",
        "description": "Lease lost thread binding while desired and observed state still disagree.",
    },
    "diverged": {
        "title": "Diverged",
        "description": "Lease is still attached to a thread, but runtime state has not converged.",
    },
    "orphan": {
        "title": "Orphans",
        "description": "Lease has no active thread binding. Usually cleanup or historical residue.",
    },
    "healthy": {
        "title": "Healthy",
        "description": "Lease has a thread binding and desired state matches observed state.",
    },
}


LEASE_TRIAGE_ORDER = [
    "active_drift",
    "detached_residue",
    "orphan_cleanup",
    "healthy_capacity",
]

LEASE_TRIAGE_META = {
    "active_drift": {
        "title": "Active Drift",
        "description": "Leases whose desired and observed state still disagree recently enough to warrant active operator attention.",
        "tone": "warning",
    },
    "detached_residue": {
        "title": "Detached Residue",
        "description": (
            "Leases still marked desired=running but observed=detached long after the runtime "
            "stopped moving. Usually cleanup debt, not live pressure."
        ),
        "tone": "danger",
    },
    "orphan_cleanup": {
        "title": "Orphan Cleanup",
        "description": "Lease rows that have already lost thread binding and mainly represent cleanup backlog or historical residue.",
        "tone": "warning",
    },
    "healthy_capacity": {
        "title": "Healthy Capacity",
        "description": "Leases with attached thread context and converged runtime state.",
        "tone": "success",
    },
}

DETACHED_RESIDUE_THRESHOLD_HOURS = 4.0


def _classify_lease_semantics(*, thread_id: str | None, badge: dict[str, Any]) -> dict[str, str]:
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
    meta = LEASE_SEMANTIC_META[category]
    return {
        "category": category,
        "title": meta["title"],
        "description": meta["description"],
    }


def _parse_local_timestamp(iso_timestamp: str | None) -> datetime | None:
    if not iso_timestamp:
        return None
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


def _classify_lease_triage(
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

    meta = LEASE_TRIAGE_META[key]
    return {
        "category": key,
        "title": meta["title"],
        "description": meta["description"],
        "tone": meta["tone"],
        "age_hours": age_hours,
    }


def _triage_category_for_row(row: dict[str, Any]) -> str:
    badge = _make_badge(row.get("desired_state"), row.get("observed_state"))
    triage = _classify_lease_triage(
        thread_id=row.get("thread_id"),
        badge=badge,
        observed_state=row.get("observed_state"),
        desired_state=row.get("desired_state"),
        updated_at=row.get("updated_at"),
    )
    return str(triage["category"])


def _evaluation_no_runs_surface() -> dict[str, Any]:
    return {
        "status": "idle",
        "kind": "no_recorded_runs",
        "tone": "default",
        "headline": "No persisted evaluation runs are available yet.",
        "summary": "Evaluation storage is wired, but there are no recorded runs to report yet.",
        "facts": [{"label": "Status", "value": "idle"}],
        "artifacts": [],
        "artifact_summary": {"present": 0, "missing": 0, "total": 0},
        "next_steps": ["Run an evaluation to populate the operator surface with persisted runtime truth."],
        "raw_notes": None,
    }


def _normalize_persisted_eval_status(raw_status: str | None) -> tuple[str, str, str, str]:
    status = str(raw_status or "").strip().lower()
    # @@@eval-status-normalization - persisted eval_runs only record coarse terminal status,
    # so monitor must normalize them without pretending the old manifest/thread truth still exists.
    if status == "running":
        return (
            "running",
            "running_recorded",
            "default",
            "Latest persisted evaluation run is still marked running.",
        )
    if status in {"error", "failed", "cancelled"}:
        return (
            "completed_with_errors",
            "run_recorded_with_errors",
            "warning",
            "Latest persisted evaluation run finished with errors.",
        )
    if status == "completed":
        return (
            "completed",
            "completed_recorded",
            "success",
            "Latest persisted evaluation run completed successfully.",
        )
    return (
        "provisional",
        "persisted_status_unknown",
        "warning",
        "Latest persisted evaluation run reported an unknown status.",
    )


def _build_persisted_evaluation_surface(run: dict[str, Any], metrics_rows: list[dict[str, Any]]) -> dict[str, Any]:
    status, kind, tone, headline = _normalize_persisted_eval_status(run.get("status"))
    metrics_by_tier = {str(row.get("tier") or "").strip().lower(): row.get("metrics") or {} for row in metrics_rows}
    system_metrics = metrics_by_tier.get("system") or {}
    objective_metrics = metrics_by_tier.get("objective") or {}
    facts = [
        {"label": "Status", "value": status},
        {"label": "Run ID", "value": str(run.get("id") or "-")},
        {"label": "Thread ID", "value": str(run.get("thread_id") or "-")},
        {"label": "Started At", "value": str(run.get("started_at") or "-")},
        {"label": "Finished At", "value": str(run.get("finished_at") or "-")},
        {"label": "Metric Tiers", "value": str(len(metrics_rows))},
    ]
    user_message = str(run.get("user_message") or "").strip()
    if user_message:
        facts.append({"label": "User Message", "value": user_message})
    total_tokens = system_metrics.get("total_tokens")
    if total_tokens is not None:
        facts.append({"label": "Total tokens", "value": str(total_tokens)})
    llm_call_count = system_metrics.get("llm_call_count")
    if llm_call_count is not None:
        facts.append({"label": "LLM calls", "value": str(llm_call_count)})
    tool_call_count = system_metrics.get("tool_call_count")
    if tool_call_count is not None:
        facts.append({"label": "Tool calls", "value": str(tool_call_count)})
    total_duration_ms = objective_metrics.get("total_duration_ms")
    if total_duration_ms is not None:
        duration_value = int(total_duration_ms) if float(total_duration_ms).is_integer() else total_duration_ms
        facts.append({"label": "Duration (ms)", "value": str(duration_value)})

    return {
        "status": status,
        "kind": kind,
        "tone": tone,
        "headline": headline,
        "summary": (
            "Monitor is reading the latest persisted eval run from eval_runs/eval_metrics. "
            "Legacy manifest, artifact, and thread-materialization detail are not wired in this slice."
        ),
        "facts": facts,
        "artifacts": [],
        "artifact_summary": {"present": 0, "missing": 0, "total": 0},
        "next_steps": [
            "Use the persisted run and metric facts here as the current source of truth.",
            "Restore richer artifact and thread drilldown in later evaluation runtime slices if still needed.",
        ],
        "raw_notes": None,
    }


def get_monitor_evaluation_truth() -> dict[str, Any]:
    store = make_eval_store()
    runs = store.list_runs(limit=1)
    if not runs:
        return _evaluation_no_runs_surface()
    latest_run = runs[0]
    metrics_rows = store.get_metrics(str(latest_run.get("id") or ""))
    return _build_persisted_evaluation_surface(latest_run, metrics_rows)


def build_monitor_evaluation_dashboard_summary(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "unavailable")
    return {
        "evaluations_running": 1 if status == "running" else 0,
        "latest_evaluation": {
            "status": status,
            "kind": payload.get("kind"),
            "tone": payload.get("tone"),
            "headline": payload.get("headline"),
        },
    }


def _map_leases(rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for row in rows:
        badge = _make_badge(row["desired_state"], row["observed_state"])
        triage = _classify_lease_triage(
            thread_id=row["thread_id"],
            badge=badge,
            observed_state=row["observed_state"],
            desired_state=row["desired_state"],
            updated_at=row["updated_at"],
        )
        items.append(
            {
                "lease_id": row["lease_id"],
                "provider": row["provider_name"],
                "instance_id": row["current_instance_id"],
                "thread": _thread_ref(row["thread_id"]),
                "state_badge": badge,
                "semantics": _classify_lease_semantics(thread_id=row["thread_id"], badge=badge),
                "triage": triage,
                "error": row["last_error"],
                "updated_at": row["updated_at"],
                "updated_ago": _format_time_ago(row["updated_at"]),
            }
        )

    summary = {key: 0 for key in LEASE_SEMANTIC_ORDER}
    for item in items:
        summary[item["semantics"]["category"]] += 1
    summary["total"] = len(items)

    groups = []
    for key in LEASE_SEMANTIC_ORDER:
        meta = LEASE_SEMANTIC_META[key]
        group_items = [item for item in items if item["semantics"]["category"] == key]
        groups.append(
            {
                "key": key,
                "title": meta["title"],
                "description": meta["description"],
                "count": len(group_items),
                "items": group_items,
            }
        )

    triage_summary = {key: 0 for key in LEASE_TRIAGE_ORDER}
    for item in items:
        triage_summary[item["triage"]["category"]] += 1
    triage_summary["total"] = len(items)

    triage_groups = []
    for key in LEASE_TRIAGE_ORDER:
        meta = LEASE_TRIAGE_META[key]
        group_items = [item for item in items if item["triage"]["category"] == key]
        triage_groups.append(
            {
                "key": key,
                "title": meta["title"],
                "description": meta["description"],
                "tone": meta["tone"],
                "count": len(group_items),
                "items": group_items,
            }
        )

    return {
        "title": "All Leases",
        "count": len(items),
        "summary": summary,
        "groups": groups,
        "triage": {
            "summary": triage_summary,
            "groups": triage_groups,
        },
        "items": items,
    }

def list_leases() -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        return _map_leases(repo.query_leases())
    finally:
        repo.close()


# ---------------------------------------------------------------------------
# Public API: diagnostics
# ---------------------------------------------------------------------------
