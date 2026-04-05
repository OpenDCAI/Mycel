"""Monitor service: sandbox lease/thread observation + health diagnostics."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from backend.web.services.sandbox_service import init_providers_and_managers, load_all_sessions
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path
from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo

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
    items = [
        {
            "lease_id": row["lease_id"],
            "lease_url": f"/lease/{row['lease_id']}",
            "provider": row["provider_name"],
            "instance_id": row["current_instance_id"],
            "thread": _thread_ref(row["thread_id"]),
            "state_badge": _make_badge(row["desired_state"], row["observed_state"]),
            "error": row["last_error"],
            "updated_at": row["updated_at"],
            "updated_ago": _format_time_ago(row["updated_at"]),
        }
        for row in rows
    ]
    return {"title": "All Leases", "count": len(items), "items": items}


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
    repo = SQLiteSandboxMonitorRepo()
    try:
        return _map_threads(repo.query_threads())
    finally:
        repo.close()


def get_thread(thread_id: str) -> dict[str, Any]:
    repo = SQLiteSandboxMonitorRepo()
    try:
        summary = repo.query_thread_summary(thread_id)
        if not summary:
            raise KeyError("Thread not found")
        return _map_thread_detail(thread_id, repo.query_thread_sessions(thread_id))
    finally:
        repo.close()


def list_leases() -> dict[str, Any]:
    repo = SQLiteSandboxMonitorRepo()
    try:
        return _map_leases(repo.query_leases())
    finally:
        repo.close()


def get_lease(lease_id: str) -> dict[str, Any]:
    repo = SQLiteSandboxMonitorRepo()
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
    repo = SQLiteSandboxMonitorRepo()
    try:
        return _map_diverged(repo.query_diverged())
    finally:
        repo.close()


def list_events(limit: int = 100) -> dict[str, Any]:
    repo = SQLiteSandboxMonitorRepo()
    try:
        return _map_events(repo.query_events(limit))
    finally:
        repo.close()


def get_event(event_id: str) -> dict[str, Any]:
    repo = SQLiteSandboxMonitorRepo()
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
        repo = SQLiteSandboxMonitorRepo()
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
