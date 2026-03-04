"""Observe capabilities for monitor core."""

from typing import Any

from . import mappers, queries


def list_threads() -> dict[str, Any]:
    with queries.connect_db() as db:
        rows = queries.query_threads(db)
    return mappers.map_threads(rows)


def get_thread(thread_id: str) -> dict[str, Any]:
    with queries.connect_db() as db:
        sessions = queries.query_thread_sessions(db, thread_id)
    return mappers.map_thread_detail(thread_id, sessions)


def list_leases() -> dict[str, Any]:
    with queries.connect_db() as db:
        rows = queries.query_leases(db)
    return mappers.map_leases(rows)


def get_lease(lease_id: str) -> dict[str, Any]:
    with queries.connect_db() as db:
        lease = queries.query_lease(db, lease_id)
        if not lease:
            raise KeyError("Lease not found")
        threads = queries.query_lease_threads(db, lease_id)
        events = queries.query_lease_events(db, lease_id)
    return mappers.map_lease_detail(lease_id, lease, threads, events)


def list_diverged() -> dict[str, Any]:
    with queries.connect_db() as db:
        rows = queries.query_diverged(db)
    return mappers.map_diverged(rows)


def list_events(limit: int = 100) -> dict[str, Any]:
    with queries.connect_db() as db:
        rows = queries.query_events(db, limit)
    return mappers.map_events(rows)


def get_event(event_id: str) -> dict[str, Any]:
    with queries.connect_db() as db:
        event = queries.query_event(db, event_id)
    if not event:
        raise KeyError("Event not found")
    return mappers.map_event_detail(event_id, event)
