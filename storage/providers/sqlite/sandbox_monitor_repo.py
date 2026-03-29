"""SQLite read-only queries against the sandbox DB for monitoring."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite_role

logger = logging.getLogger(__name__)


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
            WHERE cs.status != 'closed'
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
                sl.recipe_id,
                sl.desired_state,
                sl.observed_state,
                sl.current_instance_id,
                sl.last_error,
                sl.updated_at,
                MAX(cs.thread_id) as thread_id
            FROM sandbox_leases sl
            LEFT JOIN chat_sessions cs ON sl.lease_id = cs.lease_id AND cs.status != 'closed'
            GROUP BY sl.lease_id
            ORDER BY sl.updated_at DESC
            """
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def list_leases_with_threads(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT
                sl.lease_id,
                sl.provider_name,
                sl.recipe_id,
                sl.desired_state,
                sl.observed_state,
                sl.updated_at,
                at.thread_id,
                at.cwd
            FROM sandbox_leases sl
            LEFT JOIN abstract_terminals at ON sl.lease_id = at.lease_id
            ORDER BY sl.updated_at DESC, at.created_at DESC
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
            "SELECT DISTINCT thread_id FROM chat_sessions WHERE lease_id = ? AND status != 'closed'",
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
                    (julianday('now', 'utc') - julianday(sl.updated_at)) * 24
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
        """Leases with crew info for resource overview.

        @@@lease-source-of-truth - sandbox_leases is the source of truth for sandboxes.
        chat_sessions is LEFT JOIN'd for crew info only, filtered to non-closed to avoid
        returning phantom rows for stale/reopened sessions on the same lease.
        @@@thread-id-permanent - thread_id is resolved via COALESCE: prefer the active
        session's thread_id, fall back to the most recent session (including closed).
        This ensures agent name is never lost when a sandbox is paused between runs.
        """
        if not self._table_exists("sandbox_leases"):
            return []
        rows = self._conn.execute(
            """
            SELECT
                sl.lease_id AS lease_id,
                sl.provider_name AS provider,
                sl.observed_state AS observed_state,
                sl.desired_state AS desired_state,
                sl.created_at AS created_at,
                cs.chat_session_id AS session_id,
                COALESCE(
                    cs.thread_id,
                    (SELECT thread_id FROM chat_sessions
                     WHERE lease_id = sl.lease_id
                     ORDER BY started_at DESC LIMIT 1)
                ) AS thread_id
            FROM sandbox_leases sl
            LEFT JOIN chat_sessions cs
                ON sl.lease_id = cs.lease_id
                AND cs.status != 'closed'
            ORDER BY sl.created_at DESC
            """
        ).fetchall()
        return [
            {
                "provider": (r["provider"] or "local"),
                "session_id": r["session_id"],
                "thread_id": r["thread_id"],
                "lease_id": r["lease_id"],
                "observed_state": r["observed_state"],
                "desired_state": r["desired_state"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def list_probe_targets(self) -> list[dict]:
        """Active lease instances eligible for resource probing.

        @@@probe-instance-id - Uses provider_session_id from sandbox_instances
        (the ID the provider recognizes), falling back to current_instance_id.
        """
        if not self._table_exists("sandbox_leases"):
            logger.warning("sandbox_leases table does not exist")
            return []

        has_instances = self._table_exists("sandbox_instances")

        if has_instances:
            rows = self._conn.execute(
                """
                SELECT DISTINCT
                    sl.lease_id,
                    sl.provider_name,
                    COALESCE(si.provider_session_id, sl.current_instance_id) as instance_id,
                    sl.observed_state
                FROM sandbox_leases sl
                LEFT JOIN sandbox_instances si ON sl.lease_id = si.lease_id
                WHERE sl.observed_state IN ('running', 'detached', 'paused')
                  AND COALESCE(si.provider_session_id, sl.current_instance_id) IS NOT NULL
                  AND COALESCE(si.provider_session_id, sl.current_instance_id) != ''
                ORDER BY sl.updated_at DESC
                """
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT
                    sl.lease_id,
                    sl.provider_name,
                    sl.current_instance_id as instance_id,
                    sl.observed_state
                FROM sandbox_leases sl
                WHERE sl.observed_state IN ('running', 'detached', 'paused')
                  AND sl.current_instance_id IS NOT NULL
                  AND sl.current_instance_id != ''
                ORDER BY sl.updated_at DESC
                """
            ).fetchall()

        logger.info(f"list_probe_targets query returned {len(rows)} rows")

        targets: list[dict] = []
        for row in rows:
            lease_id = str(row["lease_id"] or "").strip()
            provider_name = str(row["provider_name"] or "").strip()
            instance_id = str(row["instance_id"] or "").strip()
            observed_state = str(row["observed_state"] or "unknown").strip().lower()
            if lease_id and provider_name and instance_id:
                targets.append({
                    "lease_id": lease_id,
                    "provider_name": provider_name,
                    "instance_id": instance_id,
                    "observed_state": observed_state,
                })

        logger.info(f"list_probe_targets returning {len(targets)} targets")
        return targets

    def query_lease_instance_id(self, lease_id: str) -> str | None:
        """Effective instance_id for a lease (COALESCE sandbox_instances + current_instance_id)."""
        if self._table_exists("sandbox_instances"):
            row = self._conn.execute(
                """
                SELECT COALESCE(si.provider_session_id, sl.current_instance_id) as instance_id
                FROM sandbox_leases sl
                LEFT JOIN sandbox_instances si ON sl.lease_id = si.lease_id
                WHERE sl.lease_id = ?
                """,
                (lease_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT current_instance_id as instance_id FROM sandbox_leases WHERE lease_id = ?",
                (lease_id,),
            ).fetchone()
        if not row:
            return None
        val = str(row["instance_id"] or "").strip()
        return val or None

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
