"""SQLite repository for summaries persistence."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from storage.providers.sqlite.connection import create_connection


class SQLiteSummaryRepo:
    """Repository boundary for summaries table operations."""

    def __init__(
        self,
        db_path: Path | str,
        conn: sqlite3.Connection | None = None,
        connect_fn: Callable[[Path | str], sqlite3.Connection] | None = None,
    ) -> None:
        self._connect_fn = connect_fn
        self._db_path = db_path
        self._own_conn = conn is None and connect_fn is None
        if conn is not None:
            self._conn = conn
        elif connect_fn is not None:
            self._conn = None
        else:
            self._conn = create_connection(db_path, row_factory=sqlite3.Row)

    @contextmanager
    def _connection(self):
        if self._connect_fn is None:
            if self._conn is None:
                raise RuntimeError("SQLiteSummaryRepo connection is not initialized")
            yield self._conn
            return

        conn = self._connect_fn(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def ensure_tables(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS summaries (
                    summary_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    summary_text TEXT NOT NULL,
                    compact_up_to_index INTEGER NOT NULL,
                    compacted_at INTEGER NOT NULL,
                    is_split_turn BOOLEAN DEFAULT FALSE,
                    split_turn_prefix TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_summaries_thread_id
                ON summaries(thread_id, is_active, created_at DESC)
                """
            )
            conn.commit()

    def close(self) -> None:
        if self._own_conn and self._conn is not None:
            self._conn.close()

    def save_summary(
        self,
        summary_id: str,
        thread_id: str,
        summary_text: str,
        compact_up_to_index: int,
        compacted_at: int,
        is_split_turn: bool,
        split_turn_prefix: str | None,
        created_at: str,
    ) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE summaries
                SET is_active = FALSE
                WHERE thread_id = ? AND is_active = TRUE
                """,
                (thread_id,),
            )
            conn.execute(
                """
                INSERT INTO summaries (
                    summary_id, thread_id, summary_text,
                    compact_up_to_index, compacted_at,
                    is_split_turn, split_turn_prefix,
                    is_active, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary_id,
                    thread_id,
                    summary_text,
                    compact_up_to_index,
                    compacted_at,
                    is_split_turn,
                    split_turn_prefix,
                    True,
                    created_at,
                ),
            )
            conn.commit()

    def get_latest_summary_row(self, thread_id: str) -> dict[str, object] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT summary_id, thread_id, summary_text,
                       compact_up_to_index, compacted_at,
                       is_split_turn, split_turn_prefix,
                       is_active, created_at
                FROM summaries
                WHERE thread_id = ? AND is_active = TRUE
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_summaries(self, thread_id: str) -> list[dict[str, object]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT summary_id, thread_id,
                       compact_up_to_index, compacted_at,
                       is_split_turn, is_active, created_at
                FROM summaries
                WHERE thread_id = ?
                ORDER BY created_at DESC
                """,
                (thread_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_thread_summaries(self, thread_id: str) -> None:
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM summaries WHERE thread_id = ?",
                (thread_id,),
            )
            conn.commit()
