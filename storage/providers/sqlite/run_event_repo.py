"""SQLite repository for run event persistence operations."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from storage.providers.sqlite.connection import create_connection


class SQLiteRunEventRepo:
    """Minimal run event repository with parameterized SQL operations.

    Thread-safe: all connection access is serialized via a lock, allowing
    concurrent ``asyncio.to_thread`` callers from the event loop.
    """

    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            if db_path is None:
                db_path = Path.home() / ".leon" / "events.db"
            self._conn = create_connection(db_path)
        self._ensure_table()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def append_event(
        self,
        thread_id: str,
        run_id: str,
        event_type: str,
        data: dict[str, Any],
        message_id: str | None = None,
    ) -> int:
        payload = json.dumps(data, ensure_ascii=False)
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO run_events (thread_id, run_id, event_type, data, message_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (thread_id, run_id, event_type, payload, message_id),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def list_events(
        self,
        thread_id: str,
        run_id: str,
        *,
        after: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT seq, event_type, data, message_id
                FROM run_events
                WHERE thread_id = ? AND run_id = ? AND seq > ?
                ORDER BY seq ASC
                LIMIT ?
                """,
                (thread_id, run_id, after, limit),
            ).fetchall()
        return [
            {
                "seq": row[0],
                "event_type": row[1],
                "data": json.loads(row[2]) if row[2] else {},
                "message_id": row[3],
            }
            for row in rows
        ]

    def latest_seq(self, thread_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(seq) FROM run_events WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def latest_run_id(self, thread_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT run_id
                FROM run_events
                WHERE thread_id = ?
                ORDER BY seq DESC
                LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
        return row[0] if row else None

    def list_run_ids(self, thread_id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT run_id
                FROM run_events
                WHERE thread_id = ?
                GROUP BY run_id
                ORDER BY MAX(seq) DESC
                """,
                (thread_id,),
            ).fetchall()
        return [row[0] for row in rows if row[0]]

    def delete_runs(self, thread_id: str, run_ids: list[str]) -> int:
        if not run_ids:
            return 0

        placeholders = ",".join("?" for _ in run_ids)
        # @@@param_sql - run ids can be external input; keep IN-clause values fully parameterized.
        with self._lock:
            cursor = self._conn.execute(
                f"DELETE FROM run_events WHERE thread_id = ? AND run_id IN ({placeholders})",
                [thread_id] + run_ids,
            )
            self._conn.commit()
        return int(cursor.rowcount)

    def delete_thread_events(self, thread_id: str) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM run_events WHERE thread_id = ?",
                (thread_id,),
            )
            self._conn.commit()
        return int(cursor.rowcount)

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL,
                message_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_run_events_thread_run
            ON run_events (thread_id, run_id, seq)
            """
        )
        self._conn.commit()
