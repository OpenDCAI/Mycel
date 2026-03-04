"""DTO mapping helpers for monitor core observe module."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any


def format_time_ago(iso_timestamp: str | None) -> str:
    """Convert ISO timestamp to human readable 'X hours ago'."""
    if not iso_timestamp:
        return "never"
    # @@@naive-local-time - SQLite timestamps in this module are local-time strings.
    if "Z" in iso_timestamp:
        iso_timestamp = iso_timestamp.replace("Z", "")
    if "+" in iso_timestamp:
        iso_timestamp = iso_timestamp.split("+")[0]
    dt = datetime.fromisoformat(iso_timestamp)
    now = datetime.now()
    delta = now - dt

    if delta.days > 0:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    minutes = (delta.seconds % 3600) // 60
    if minutes > 0:
        return f"{minutes}m ago"
    return "just now"


def make_badge(desired: str | None, observed: str | None) -> dict[str, Any]:
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


def _lease_ref(lease_id: str | None, provider: str | None, instance_id: str | None = None) -> dict[str, Any]:
    return {
        "lease_id": lease_id,
        "lease_url": f"/lease/{lease_id}" if lease_id else None,
        "provider": provider,
        "instance_id": instance_id,
    }


def _lease_link(lease_id: str | None) -> dict[str, Any]:
    return {"lease_id": lease_id, "lease_url": f"/lease/{lease_id}" if lease_id else None}


def map_threads(rows: list[sqlite3.Row]) -> dict[str, Any]:
    items = [
        {
            "thread_id": row["thread_id"],
            "thread_url": f"/thread/{row['thread_id']}",
            "session_count": row["session_count"],
            "last_active": row["last_active"],
            "last_active_ago": format_time_ago(row["last_active"]),
            "lease": _lease_ref(row["lease_id"], row["provider_name"], row["current_instance_id"]),
            "state_badge": make_badge(row["desired_state"], row["observed_state"]),
        }
        for row in rows
    ]
    return {"title": "All Threads", "count": len(items), "items": items}


def map_thread_detail(thread_id: str, sessions: list[sqlite3.Row]) -> dict[str, Any]:
    lease_ids = {
        str(session["lease_id"]) for session in sessions if session["lease_id"]
    }
    items = [
        {
            "session_id": session["chat_session_id"],
            "session_url": f"/session/{session['chat_session_id']}",
            "status": session["status"],
            "started_at": session["started_at"],
            "started_ago": format_time_ago(session["started_at"]),
            "ended_at": session["ended_at"],
            "ended_ago": format_time_ago(session["ended_at"]) if session["ended_at"] else None,
            "close_reason": session["close_reason"],
            "lease": _lease_ref(session["lease_id"], session["provider_name"], session["current_instance_id"]),
            "state_badge": make_badge(session["desired_state"], session["observed_state"]),
            "error": session["last_error"],
        }
        for session in sessions
    ]

    return {
        "thread_id": thread_id,
        "breadcrumb": [{"label": "Threads", "url": "/threads"}, {"label": thread_id[:8], "url": f"/thread/{thread_id}"}],
        "sessions": {"title": "Sessions", "count": len(items), "items": items},
        "related_leases": {
            "title": "Related Leases",
            "items": [{"lease_id": lease_id, "lease_url": f"/lease/{lease_id}"} for lease_id in lease_ids],
        },
    }


def map_leases(rows: list[sqlite3.Row]) -> dict[str, Any]:
    items = [
        {
            "lease_id": row["lease_id"],
            "lease_url": f"/lease/{row['lease_id']}",
            "provider": row["provider_name"],
            "instance_id": row["current_instance_id"],
            "thread": _thread_ref(row["thread_id"]),
            "state_badge": make_badge(row["desired_state"], row["observed_state"]),
            "error": row["last_error"],
            "updated_at": row["updated_at"],
            "updated_ago": format_time_ago(row["updated_at"]),
        }
        for row in rows
    ]
    return {"title": "All Leases", "count": len(items), "items": items}


def map_lease_detail(lease_id: str, lease: sqlite3.Row, threads: list[sqlite3.Row], events: list[sqlite3.Row]) -> dict[str, Any]:
    badge = make_badge(lease["desired_state"], lease["observed_state"])
    badge["error"] = lease["last_error"]

    return {
        "lease_id": lease_id,
        "breadcrumb": [{"label": "Leases", "url": "/leases"}, {"label": lease_id, "url": f"/lease/{lease_id}"}],
        "info": {
            "provider": lease["provider_name"],
            "instance_id": lease["current_instance_id"],
            "created_at": lease["created_at"],
            "created_ago": format_time_ago(lease["created_at"]),
            "updated_at": lease["updated_at"],
            "updated_ago": format_time_ago(lease["updated_at"]),
        },
        "state": badge,
        "related_threads": {
            "title": "Related Threads",
            "items": [{"thread_id": row["thread_id"], "thread_url": f"/thread/{row['thread_id']}"} for row in threads],
        },
        "lease_events": {
            "title": "Lease Events",
            "count": len(events),
            "items": [
                {
                    "event_id": event["event_id"],
                    "event_url": f"/event/{event['event_id']}",
                    "event_type": event["event_type"],
                    "source": event["source"],
                    "created_at": event["created_at"],
                    "created_ago": format_time_ago(event["created_at"]),
                }
                for event in events
            ],
        },
    }


def map_diverged(rows: list[sqlite3.Row]) -> dict[str, Any]:
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


def map_events(rows: list[sqlite3.Row]) -> dict[str, Any]:
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
            "created_ago": format_time_ago(row["created_at"]),
        }
        for row in rows
    ]

    return {
        "title": "Lease Events",
        "description": "Audit log of all lease lifecycle operations",
        "count": len(items),
        "items": items,
    }


def map_event_detail(event_id: str, event: sqlite3.Row) -> dict[str, Any]:
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
            "created_ago": format_time_ago(event["created_at"]),
        },
        "related_lease": {
            "lease_id": event["lease_id"],
            "lease_url": f"/lease/{event['lease_id']}" if event["lease_id"] else None,
        },
        "error": event["error"],
        "payload": payload,
    }
