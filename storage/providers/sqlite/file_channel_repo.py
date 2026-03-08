"""SQLite repository for thread file channels and transfers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from storage.providers.sqlite.connection import create_connection


class SQLiteFileChannelRepo:

    def __init__(self, db_path: str | Path, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        if conn is not None:
            self._conn = conn
        else:
            self._conn = create_connection(db_path)
        self._ensure_tables()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def upsert_channel(self, thread_id: str, files_path: str, now: str) -> None:
        self._conn.execute(
            """
            INSERT INTO thread_file_channels(thread_id, files_path, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                files_path = excluded.files_path,
                updated_at = excluded.updated_at
            """,
            (thread_id, files_path, now, now),
        )
        self._conn.commit()

    def get_files_path(self, thread_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT files_path FROM thread_file_channels WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        return row[0] if row else None

    def delete_channel(self, thread_id: str) -> None:
        self._conn.execute("DELETE FROM thread_file_channels WHERE thread_id = ?", (thread_id,))
        self._conn.commit()

    def record_transfer(self, thread_id: str, direction: str, relative_path: str, size_bytes: int, status: str, created_at: str) -> None:
        self._conn.execute(
            """
            INSERT INTO thread_file_transfers(thread_id, direction, relative_path, size_bytes, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (thread_id, direction, relative_path, int(size_bytes), status, created_at),
        )
        self._conn.commit()

    def list_transfers(self, thread_id: str, limit: int = 100) -> list[dict[str, Any]]:
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(
            """
            SELECT id, thread_id, direction, relative_path, size_bytes, status, created_at
            FROM thread_file_transfers
            WHERE thread_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (thread_id, max(1, int(limit))),
        ).fetchall()
        self._conn.row_factory = None
        return [dict(row) for row in rows]

    def delete_transfers(self, thread_id: str) -> None:
        self._conn.execute("DELETE FROM thread_file_transfers WHERE thread_id = ?", (thread_id,))
        self._conn.commit()

    def _ensure_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_file_channels (
                thread_id TEXT PRIMARY KEY,
                files_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_file_transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_thread_file_transfers_thread_id_created_at "
            "ON thread_file_transfers(thread_id, created_at DESC)"
        )
        self._conn.commit()
