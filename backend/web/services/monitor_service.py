"""Monitor service: sandbox lease/thread observation + health diagnostics."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from backend.web.core.storage_factory import make_sandbox_monitor_repo
from backend.web.services.sandbox_service import init_providers_and_managers, load_all_sessions
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path

# ---------------------------------------------------------------------------
# Mapping helpers (private)
# ---------------------------------------------------------------------------


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
        "thread_url": f"/thread/{thread_id}" if thread_id else None,
        "is_orphan": not thread_id,
    }


def _lease_ref(
    lease_id: str | None,
    provider: str | None,
    instance_id: str | None = None,
) -> dict[str, Any]:
    return {
        "lease_id": lease_id,
        "lease_url": f"/lease/{lease_id}" if lease_id else None,
        "provider": provider,
        "instance_id": instance_id,
    }


def _lease_link(lease_id: str | None) -> dict[str, Any]:
    return {"lease_id": lease_id, "lease_url": f"/lease/{lease_id}" if lease_id else None}


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


EVAL_NOTE_KEYS = [
    "runner",
    "rc",
    "sandbox",
    "run_dir",
    "stdout_log",
    "stderr_log",
]

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


def _extract_eval_note_value(notes: str, key: str) -> str | None:
    match = re.search(rf"(?:^|[ |]){re.escape(key)}=([^ ]+)", notes)
    if not match:
        return None
    return match.group(1).strip()


def build_evaluation_operator_surface(
    *,
    status: str,
    notes: str,
    score: dict[str, Any],
    threads_total: int,
    threads_running: int,
    threads_done: int,
) -> dict[str, Any]:
    extracted = {key: _extract_eval_note_value(notes, key) for key in EVAL_NOTE_KEYS}
    rc_text = extracted.get("rc")
    try:
        rc = int(rc_text) if rc_text is not None else None
    except ValueError:
        rc = None

    scored = bool(score.get("scored"))
    score_gate = str(score.get("score_gate") or "provisional")
    artifacts = [
        {"label": "Run directory", "path": score.get("run_dir") or extracted.get("run_dir")},
        {"label": "Run manifest", "path": score.get("manifest_path")},
        {"label": "STDOUT log", "path": extracted.get("stdout_log")},
        {"label": "STDERR log", "path": extracted.get("stderr_log")},
        {"label": "Eval summary", "path": score.get("eval_summary_path")},
        {"label": "Trace summaries", "path": score.get("trace_summaries_path")},
    ]
    artifacts = [item for item in artifacts if item["path"]]

    facts = [
        {"label": "Status", "value": status},
        {"label": "Score gate", "value": score_gate},
        {"label": "Threads materialized", "value": str(threads_total)},
        {"label": "Threads running", "value": str(threads_running)},
        {"label": "Threads done", "value": str(threads_done)},
    ]
    runner = extracted.get("runner")
    if runner:
        facts.append({"label": "Runner", "value": runner})
    if rc is not None:
        facts.append({"label": "Exit code", "value": str(rc)})

    tone = "default"
    headline = "Evaluation is still collecting runtime evidence."
    summary = "Use the artifacts below to inspect progress and confirm whether thread rows are materializing."
    next_steps = [
        "Open the run manifest to confirm the slice payload and output directory.",
        "Inspect stdout/stderr before assuming the run is healthy.",
    ]

    if status == "provisional" and not scored:
        tone = "warning"
        headline = "Evaluation is provisional. Final score is blocked."
        summary = "This run has not produced the final eval summary yet, so publishable scoring is intentionally withheld."
        next_steps = [
            "Check whether eval_summary_path is still missing because the run is ongoing or because the runner exited early.",
            "Use stdout/stderr logs to confirm whether the solve phase actually started.",
        ]

    if rc is not None and rc != 0 and threads_total == 0:
        tone = "danger"
        headline = "Runner exited before evaluation threads materialized."
        summary = "Treat this as a bootstrap failure, not as an empty successful run. No evaluation thread rows were created."
        next_steps = [
            "Inspect STDERR first to find the failing bootstrap step.",
            "Use the run manifest and stdout log to confirm whether the slice was prepared before exit.",
            "Re-run only after the failing dependency or model configuration is understood.",
        ]
    elif status == "running":
        tone = "default"
        headline = "Evaluation is actively running."
        summary = "Thread rows and traces may lag behind the runner. Use live progress and logs before declaring drift."
        next_steps = [
            "Refresh after new thread rows materialize.",
            "Inspect traces only after the first active thread appears.",
        ]
    elif status == "completed" and scored:
        tone = "success"
        headline = "Evaluation finished with a publishable score surface."
        summary = "Score artifacts are present. Use the thread table to drill into trace-level evidence."
        next_steps = [
            "Open threads with low-quality traces and inspect tool-call detail.",
            "Use the eval summary and trace summaries to compare runs.",
        ]

    return {
        "tone": tone,
        "headline": headline,
        "summary": summary,
        "facts": facts,
        "artifacts": artifacts,
        "next_steps": next_steps,
        "raw_notes": notes,
    }


# ---------------------------------------------------------------------------
# Mappers (private)
# ---------------------------------------------------------------------------


def _map_threads(rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = [
        {
            "thread_id": row["thread_id"],
            "thread_url": f"/thread/{row['thread_id']}",
            "session_count": row["session_count"],
            "last_active": row["last_active"],
            "last_active_ago": _format_time_ago(row["last_active"]),
            "lease": _lease_ref(row["lease_id"], row["provider_name"], row["current_instance_id"]),
            "state_badge": _make_badge(row["desired_state"], row["observed_state"]),
        }
        for row in rows
    ]
    return {"title": "All Threads", "count": len(items), "items": items}


def _map_thread_detail(thread_id: str, sessions: list[dict[str, Any]]) -> dict[str, Any]:
    lease_ids = {str(s["lease_id"]) for s in sessions if s["lease_id"]}
    items = [
        {
            "session_id": s["chat_session_id"],
            "session_url": f"/session/{s['chat_session_id']}",
            "status": s["status"],
            "started_at": s["started_at"],
            "started_ago": _format_time_ago(s["started_at"]),
            "ended_at": s["ended_at"],
            "ended_ago": _format_time_ago(s["ended_at"]) if s["ended_at"] else None,
            "close_reason": s["close_reason"],
            "lease": _lease_ref(s["lease_id"], s["provider_name"], s["current_instance_id"]),
            "state_badge": _make_badge(s["desired_state"], s["observed_state"]),
            "error": s["last_error"],
        }
        for s in sessions
    ]
    breadcrumb = [
        {"label": "Threads", "url": "/threads"},
        {"label": thread_id[:8], "url": f"/thread/{thread_id}"},
    ]
    return {
        "thread_id": thread_id,
        "breadcrumb": breadcrumb,
        "sessions": {"title": "Sessions", "count": len(items), "items": items},
        "related_leases": {
            "title": "Related Leases",
            "items": [{"lease_id": lid, "lease_url": f"/lease/{lid}"} for lid in lease_ids],
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
                "lease_url": f"/lease/{row['lease_id']}",
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


def _map_lease_detail(
    lease_id: str,
    lease: dict[str, Any],
    threads: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    badge = _make_badge(lease["desired_state"], lease["observed_state"])
    badge["error"] = lease["last_error"]
    return {
        "lease_id": lease_id,
        "breadcrumb": [
            {"label": "Leases", "url": "/leases"},
            {"label": lease_id, "url": f"/lease/{lease_id}"},
        ],
        "info": {
            "provider": lease["provider_name"],
            "instance_id": lease["current_instance_id"],
            "created_at": lease["created_at"],
            "created_ago": _format_time_ago(lease["created_at"]),
            "updated_at": lease["updated_at"],
            "updated_ago": _format_time_ago(lease["updated_at"]),
        },
        "state": badge,
        "related_threads": {
            "title": "Related Threads",
            "items": [{"thread_id": r["thread_id"], "thread_url": f"/thread/{r['thread_id']}"} for r in threads],
        },
        "lease_events": {
            "title": "Lease Events",
            "count": len(events),
            "items": [
                {
                    "event_id": e["event_id"],
                    "event_url": f"/event/{e['event_id']}",
                    "event_type": e["event_type"],
                    "source": e["source"],
                    "created_at": e["created_at"],
                    "created_ago": _format_time_ago(e["created_at"]),
                }
                for e in events
            ],
        },
    }


def _map_diverged(rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = [
        {
            "lease_id": row["lease_id"],
            "lease_url": f"/lease/{row['lease_id']}",
            "provider": row["provider_name"],
            "instance_id": row["current_instance_id"],
            "thread": _thread_ref(row["thread_id"]),
            "state_badge": {
                "desired": row["desired_state"],
                "observed": row["observed_state"],
                "hours_diverged": row["hours_diverged"],
                "color": "red" if row["hours_diverged"] > 24 else "yellow",
            },
            "error": row["last_error"],
        }
        for row in rows
    ]
    return {
        "title": "Diverged Leases",
        "description": "Leases where desired_state != observed_state",
        "count": len(items),
        "items": items,
    }


def _map_events(rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = [
        {
            "event_id": row["event_id"],
            "event_url": f"/event/{row['event_id']}",
            "event_type": row["event_type"],
            "source": row["source"],
            "provider": row["provider_name"],
            "lease": _lease_link(row["lease_id"]),
            "error": row["error"],
            "created_at": row["created_at"],
            "created_ago": _format_time_ago(row["created_at"]),
        }
        for row in rows
    ]
    return {
        "title": "Lease Events",
        "description": "Audit log of all lease lifecycle operations",
        "count": len(items),
        "items": items,
    }


def _map_event_detail(event_id: str, event: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(event["payload_json"]) if event["payload_json"] else {}
    return {
        "event_id": event_id,
        "breadcrumb": [
            {"label": "Events", "url": "/events"},
            {"label": event["event_type"], "url": f"/event/{event_id}"},
        ],
        "info": {
            "event_type": event["event_type"],
            "source": event["source"],
            "provider": event["provider_name"],
            "created_at": event["created_at"],
            "created_ago": _format_time_ago(event["created_at"]),
        },
        "related_lease": {
            "lease_id": event["lease_id"],
            "lease_url": f"/lease/{event['lease_id']}" if event["lease_id"] else None,
        },
        "error": event["error"],
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Public API: observe
# ---------------------------------------------------------------------------


def list_threads() -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        return _map_threads(repo.query_threads())
    finally:
        repo.close()


def get_thread(thread_id: str) -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        summary = repo.query_thread_summary(thread_id)
        if not summary:
            raise KeyError("Thread not found")
        return _map_thread_detail(thread_id, repo.query_thread_sessions(thread_id))
    finally:
        repo.close()


def list_leases() -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        return _map_leases(repo.query_leases())
    finally:
        repo.close()


def get_lease(lease_id: str) -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        lease = repo.query_lease(lease_id)
        if not lease:
            raise KeyError("Lease not found")
        threads = repo.query_lease_threads(lease_id)
        events = repo.query_lease_events(lease_id)
    finally:
        repo.close()
    return _map_lease_detail(lease_id, lease, threads, events)


def list_diverged() -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        return _map_diverged(repo.query_diverged())
    finally:
        repo.close()


def list_events(limit: int = 100) -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        return _map_events(repo.query_events(limit))
    finally:
        repo.close()


def get_event(event_id: str) -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        event = repo.query_event(event_id)
    finally:
        repo.close()
    if not event:
        raise KeyError("Event not found")
    return _map_event_detail(event_id, event)


# ---------------------------------------------------------------------------
# Public API: diagnostics
# ---------------------------------------------------------------------------


def runtime_health_snapshot() -> dict[str, Any]:
    """Lightweight control-plane health snapshot."""
    db_path = resolve_role_db_path(SQLiteDBRole.SANDBOX)
    db_exists = db_path.exists()
    tables: dict[str, int] = {"chat_sessions": 0, "sandbox_leases": 0, "lease_events": 0}

    if db_exists:
        repo = make_sandbox_monitor_repo()
        try:
            tables = repo.count_rows(list(tables))
        finally:
            repo.close()

    _, managers = init_providers_and_managers()
    sessions = load_all_sessions(managers)
    provider_counts: dict[str, int] = {}
    for session in sessions:
        provider = str(session.get("provider") or "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1

    return {
        "snapshot_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "db": {"path": str(db_path), "exists": db_exists, "counts": tables},
        "sessions": {"total": len(sessions), "providers": provider_counts},
    }
