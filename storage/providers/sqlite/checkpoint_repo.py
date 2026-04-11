"""SQLite repository for checkpoint/writes persistence operations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from storage.providers.sqlite.kernel import connect_sqlite


class SQLiteCheckpointRepo:
    """Minimal checkpoint repository for thread-level read/write cleanup."""

    _ALLOWED_TABLES = {"checkpoints", "checkpoint_writes", "checkpoint_blobs"}

    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        if conn is not None:
            self._conn = conn
            return

        if db_path is None:
            db_path = Path.home() / ".leon" / "leon.db"
        self._conn = connect_sqlite(db_path, check_same_thread=False)

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def list_thread_ids(self) -> list[str]:
        cursor = self._conn.execute(
            """
            SELECT DISTINCT thread_id
            FROM checkpoints
            WHERE thread_id IS NOT NULL
            ORDER BY thread_id
            """
        )
        return [row[0] for row in cursor.fetchall() if row[0]]

    def delete_thread_data(self, thread_id: str) -> None:
        self._delete_by_thread("checkpoints", thread_id)
        self._delete_by_thread("checkpoint_writes", thread_id)
        self._delete_by_thread("checkpoint_blobs", thread_id)
        self._conn.commit()

    def delete_checkpoints_by_ids(self, thread_id: str, checkpoint_ids: list[str]) -> None:
        if not checkpoint_ids:
            return

        self._delete_by_thread_and_checkpoint_ids("checkpoints", thread_id, checkpoint_ids)
        self._delete_by_thread_and_checkpoint_ids("checkpoint_writes", thread_id, checkpoint_ids)
        self._delete_by_thread_and_checkpoint_ids("checkpoint_blobs", thread_id, checkpoint_ids)
        self._conn.commit()

    def _table_exists(self, table: str) -> bool:
        self._validate_table(table)
        cursor = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        )
        return cursor.fetchone() is not None

    def _column_exists(self, table: str, column: str) -> bool:
        if not self._table_exists(table):
            return False
        cursor = self._conn.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())

    def _validate_table(self, table: str) -> None:
        # @@@table_whitelist - table names cannot use query parameters; enforce strict internal whitelist.
        if table not in self._ALLOWED_TABLES:
            raise ValueError(f"Unsupported table name: {table}")

    def _delete_by_thread(self, table: str, thread_id: str) -> None:
        if not self._column_exists(table, "thread_id"):
            return
        self._conn.execute(
            f"DELETE FROM {table} WHERE thread_id = ?",
            (thread_id,),
        )

    def _delete_by_thread_and_checkpoint_ids(self, table: str, thread_id: str, checkpoint_ids: list[str]) -> None:
        if not self._column_exists(table, "thread_id"):
            return
        if not self._column_exists(table, "checkpoint_id"):
            return

        placeholders = ",".join("?" for _ in checkpoint_ids)
        # @@@param_sql - checkpoint ids are user-derived; keep parameterized placeholders for safe deletion.
        self._conn.execute(
            f"DELETE FROM {table} WHERE thread_id = ? AND checkpoint_id IN ({placeholders})",
            [thread_id] + checkpoint_ids,
        )
