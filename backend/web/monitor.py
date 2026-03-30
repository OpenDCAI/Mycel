"""
Sandbox Monitor API - View-Ready Endpoints

All endpoints return view-ready data that frontend can directly render.
No business logic in frontend.
"""

import json
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from backend.web.services import monitor_service
from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite, resolve_role_db_path

SANDBOX_DB_PATH = resolve_role_db_path(SQLiteDBRole.SANDBOX)

router = APIRouter(prefix="/api/monitor")


def get_db():
    db = connect_sqlite(SANDBOX_DB_PATH, row_factory=sqlite3.Row)
    try:
        yield db
    finally:
        db.close()


def format_time_ago(iso_timestamp: str) -> str:
    """Convert ISO timestamp to human readable 'X hours ago'"""
    if not iso_timestamp:
        return "never"
    # @@@ naive-local — SQLite timestamps are local time, compare with local now
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


def make_badge(desired, observed):
    """Build a state badge dict handling null states"""
    if not desired and not observed:
        return {"desired": None, "observed": None, "converged": True, "color": "green", "text": "destroyed"}
    if desired == observed:
        return {"desired": desired, "observed": observed, "converged": True, "color": "green", "text": observed}
    return {
        "desired": desired,
        "observed": observed,
        "converged": False,
        "color": "yellow",
        "text": f"{observed} → {desired}",
    }


@router.get("/threads")
def list_threads(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("""
        SELECT
            cs.thread_id,
            COUNT(DISTINCT cs.chat_session_id) as session_count,
            MAX(cs.last_active_at) as last_active,
            sl.lease_id,
            sl.provider_name,
            sl.desired_state,
            sl.observed_state,
            sl.current_instance_id
        FROM chat_sessions cs
        LEFT JOIN sandbox_leases sl ON cs.lease_id = sl.lease_id
        GROUP BY cs.thread_id
        ORDER BY MAX(cs.last_active_at) DESC
    """).fetchall()

    items = []
    for row in rows:
        badge = make_badge(row["desired_state"], row["observed_state"])
        items.append(
            {
                "thread_id": row["thread_id"],
                "thread_url": f"/thread/{row['thread_id']}",
                "session_count": row["session_count"],
                "last_active": row["last_active"],
                "last_active_ago": format_time_ago(row["last_active"]),
                "lease": {
                    "lease_id": row["lease_id"],
                    "lease_url": f"/lease/{row['lease_id']}" if row["lease_id"] else None,
                    "provider": row["provider_name"],
                    "instance_id": row["current_instance_id"],
                },
                "state_badge": badge,
            }
        )

    return {"title": "All Threads", "count": len(items), "items": items}


@router.get("/thread/{thread_id}")
def get_thread(thread_id: str, db: sqlite3.Connection = Depends(get_db)):
    sessions = db.execute(
        """
        SELECT
            cs.chat_session_id,
            cs.status,
            cs.started_at,
            cs.ended_at,
            cs.close_reason,
            cs.lease_id,
            sl.provider_name,
            sl.desired_state,
            sl.observed_state,
            sl.current_instance_id,
            sl.last_error
        FROM chat_sessions cs
        LEFT JOIN sandbox_leases sl ON cs.lease_id = sl.lease_id
        WHERE cs.thread_id = ?
        ORDER BY cs.started_at DESC
    """,
        (thread_id,),
    ).fetchall()

    session_items = []
    lease_ids = set()

    for s in sessions:
        if s["lease_id"]:
            lease_ids.add(s["lease_id"])

        session_items.append(
            {
                "session_id": s["chat_session_id"],
                "session_url": f"/session/{s['chat_session_id']}",
                "status": s["status"],
                "started_at": s["started_at"],
                "started_ago": format_time_ago(s["started_at"]),
                "ended_at": s["ended_at"],
                "ended_ago": format_time_ago(s["ended_at"]) if s["ended_at"] else None,
                "close_reason": s["close_reason"],
                "lease": {
                    "lease_id": s["lease_id"],
                    "lease_url": f"/lease/{s['lease_id']}" if s["lease_id"] else None,
                    "provider": s["provider_name"],
                    "instance_id": s["current_instance_id"],
                },
                "state_badge": make_badge(s["desired_state"], s["observed_state"]),
                "error": s["last_error"],
            }
        )

    return {
        "thread_id": thread_id,
        "breadcrumb": [
            {"label": "Threads", "url": "/threads"},
            {"label": thread_id[:8], "url": f"/thread/{thread_id}"},
        ],
        "sessions": {"title": "Sessions", "count": len(session_items), "items": session_items},
        "related_leases": {
            "title": "Related Leases",
            "items": [{"lease_id": lid, "lease_url": f"/lease/{lid}"} for lid in lease_ids],
        },
    }


@router.get("/leases")
def list_leases(db: sqlite3.Connection = Depends(get_db)):
    return monitor_service.list_leases()


@router.get("/lease/{lease_id}")
def get_lease(lease_id: str, db: sqlite3.Connection = Depends(get_db)):
    try:
        return monitor_service.get_lease(lease_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/diverged")
def list_diverged(db: sqlite3.Connection = Depends(get_db)):
    return monitor_service.list_diverged()


@router.get("/events")
def list_events(limit: int = 100, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        """
        SELECT le.event_id, le.lease_id, le.event_type, le.source,
               le.payload_json, le.error, le.created_at,
               sl.provider_name
        FROM lease_events le
        LEFT JOIN sandbox_leases sl ON le.lease_id = sl.lease_id
        ORDER BY le.created_at DESC
        LIMIT ?
    """,
        (limit,),
    ).fetchall()

    items = []
    for row in rows:
        items.append(
            {
                "event_id": row["event_id"],
                "event_url": f"/event/{row['event_id']}",
                "event_type": row["event_type"],
                "source": row["source"],
                "provider": row["provider_name"],
                "lease": {
                    "lease_id": row["lease_id"],
                    "lease_url": f"/lease/{row['lease_id']}" if row["lease_id"] else None,
                },
                "error": row["error"],
                "created_at": row["created_at"],
                "created_ago": format_time_ago(row["created_at"]),
            }
        )

    return {
        "title": "Lease Events",
        "description": "Audit log of all lease lifecycle operations",
        "count": len(items),
        "items": items,
    }


@router.get("/event/{event_id}")
def get_event(event_id: str, db: sqlite3.Connection = Depends(get_db)):
    event = db.execute(
        """
        SELECT le.*, sl.provider_name
        FROM lease_events le
        LEFT JOIN sandbox_leases sl ON le.lease_id = sl.lease_id
        WHERE le.event_id = ?
    """,
        (event_id,),
    ).fetchone()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

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
