"""SQLite read-only queries against the sandbox DB for monitoring."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite_role


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class SQLiteSandboxMonitorRepo:
    """Read-only monitor queries backed by the sandbox SQLite database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._conn = connect_sqlite_role(
            SQLiteDBRole.SANDBOX,
            db_path=db_path,
            row_factory=sqlite3.Row,
            check_same_thread=False,
        )

    def close(self) -> None:
        self._conn.close()

    def query_threads(self) -> list[dict]:
        rows = self._conn.execute(
            """
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
            """
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def query_thread_sessions(self, thread_id: str) -> list[dict]:
        rows = self._conn.execute(
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
        return [_row_to_dict(r) for r in rows]

    def query_leases(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT
                sl.lease_id,
                sl.provider_name,
                sl.desired_state,
                sl.observed_state,
                sl.current_instance_id,
                sl.last_error,
                sl.updated_at,
                MAX(cs.thread_id) as thread_id
            FROM sandbox_leases sl
            LEFT JOIN chat_sessions cs ON sl.lease_id = cs.lease_id
            GROUP BY sl.lease_id
            ORDER BY sl.updated_at DESC
            """
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def query_lease(self, lease_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM sandbox_leases WHERE lease_id = ?",
            (lease_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None

    def query_lease_threads(self, lease_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT DISTINCT thread_id FROM chat_sessions WHERE lease_id = ?",
            (lease_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def query_lease_events(self, lease_id: str) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT * FROM lease_events
            WHERE lease_id = ?
            ORDER BY created_at DESC
            """,
            (lease_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def query_diverged(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT
                sl.lease_id,
                sl.provider_name,
                sl.desired_state,
                sl.observed_state,
                sl.current_instance_id,
                sl.last_error,
                sl.updated_at,
                cs.thread_id,
                CAST(
                    (julianday('now', 'localtime') - julianday(sl.updated_at)) * 24
                    AS INTEGER
                ) as hours_diverged
            FROM sandbox_leases sl
            LEFT JOIN chat_sessions cs ON sl.lease_id = cs.lease_id
            WHERE sl.desired_state != sl.observed_state
            ORDER BY hours_diverged DESC
            """
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def query_events(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
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
        return [_row_to_dict(r) for r in rows]

    def list_sessions_with_leases(self) -> list[dict]:
        """Sessions joined with lease info for resource overview."""
        if not self._table_exists("chat_sessions") or not self._table_exists("sandbox_leases"):
            return []
        rows = self._conn.execute(
            """
            SELECT
                cs.chat_session_id AS session_id,
                cs.thread_id AS thread_id,
                cs.lease_id AS lease_id,
                cs.status AS status,
                cs.started_at AS created_at,
                sl.provider_name AS provider
            FROM chat_sessions cs
            LEFT JOIN sandbox_leases sl ON cs.lease_id = sl.lease_id
            ORDER BY cs.started_at DESC
            """
        ).fetchall()
        return [
            {
                "provider": (r["provider"] or "local"),
                "session_id": r["session_id"],
                "thread_id": r["thread_id"],
                "lease_id": r["lease_id"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def list_probe_targets(self) -> list[dict]:
        """Active lease instances eligible for resource probing."""
        if not self._table_exists("sandbox_leases"):
            return []
        rows = self._conn.execute(
            """
            SELECT lease_id, provider_name, current_instance_id, observed_state
            FROM sandbox_leases
            WHERE current_instance_id IS NOT NULL
              AND observed_state IN ('running', 'paused')
            ORDER BY updated_at DESC
            """
        ).fetchall()
        targets: list[dict] = []
        for row in rows:
            lease_id = str(row["lease_id"] or "").strip()
            provider_name = str(row["provider_name"] or "").strip()
            instance_id = str(row["current_instance_id"] or "").strip()
            observed_state = str(row["observed_state"] or "unknown").strip().lower()
            if lease_id and provider_name and instance_id:
                targets.append({
                    "lease_id": lease_id,
                    "provider_name": provider_name,
                    "instance_id": instance_id,
                    "observed_state": observed_state,
                })
        return targets

    def _table_exists(self, table_name: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
            (table_name,),
        ).fetchone()
        return row is not None

    def query_event(self, event_id: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT le.*, sl.provider_name
            FROM lease_events le
            LEFT JOIN sandbox_leases sl ON le.lease_id = sl.lease_id
            WHERE le.event_id = ?
            """,
            (event_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
