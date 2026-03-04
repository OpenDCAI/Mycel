"""SQLite repository for file_operations persistence."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from storage.models import FileOperationRow  # noqa: F401 — re-exported for backwards compat
from storage.providers.sqlite.connection import create_connection

logger = logging.getLogger(__name__)


class SQLiteFileOperationRepo:
    """Repository boundary for file_operations table."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            if db_path is None:
                db_path = Path.home() / ".leon" / "file_ops.db"
            self._conn = create_connection(db_path, row_factory=sqlite3.Row)
        self._ensure_table()

    @property
    def db_path(self) -> Path:
        with self._lock:
            return Path(self._conn.execute("PRAGMA database_list").fetchone()[2])

    def record(
        self,
        thread_id: str,
        checkpoint_id: str,
        operation_type: str,
        file_path: str,
        before_content: str | None,
        after_content: str,
        changes: list[dict] | None = None,
    ) -> str:
        op_id = str(uuid.uuid4())
        try:
            with self._lock:
                self._conn.execute(
                    """
                    INSERT INTO file_operations
                    (id, thread_id, checkpoint_id, timestamp, operation_type,
                     file_path, before_content, after_content, changes, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        op_id,
                        thread_id,
                        checkpoint_id,
                        time.time(),
                        operation_type,
                        file_path,
                        before_content,
                        after_content,
                        json.dumps(changes) if changes else None,
                        "applied",
                    ),
                )
                self._conn.commit()
        except Exception:
            logger.error("Failed to record file operation %s for %s", op_id, file_path, exc_info=True)
        return op_id

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def get_operations_for_thread(self, thread_id: str, status: str = "applied") -> list[FileOperationRow]:
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT * FROM file_operations
                WHERE thread_id = ? AND status = ?
                ORDER BY timestamp ASC
                """,
                (thread_id, status),
            )
            rows = cursor.fetchall()
        return [self._row_to_operation(row) for row in rows]

    def get_operations_after_checkpoint(self, thread_id: str, checkpoint_id: str) -> list[FileOperationRow]:
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT MIN(timestamp) as ts FROM file_operations
                WHERE thread_id = ? AND checkpoint_id = ?
                """,
                (thread_id, checkpoint_id),
            )
            row = cursor.fetchone()
            if not row or row["ts"] is None:
                cursor = self._conn.execute(
                    """
                    SELECT * FROM file_operations
                    WHERE thread_id = ? AND status = 'applied'
                    ORDER BY timestamp DESC
                    """,
                    (thread_id,),
                )
            else:
                target_ts = row["ts"]
                cursor = self._conn.execute(
                    """
                    SELECT * FROM file_operations
                    WHERE thread_id = ? AND timestamp >= ? AND status = 'applied'
                    ORDER BY timestamp DESC
                    """,
                    (thread_id, target_ts),
                )
            rows = cursor.fetchall()
        return [self._row_to_operation(row) for row in rows]

    def get_operations_between_checkpoints(
        self,
        thread_id: str,
        from_checkpoint_id: str,
        to_checkpoint_id: str,
    ) -> list[FileOperationRow]:
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT * FROM file_operations
                WHERE thread_id = ?
                AND checkpoint_id != ?
                AND status = 'applied'
                ORDER BY timestamp DESC
                """,
                (thread_id, from_checkpoint_id),
            )
            rows = cursor.fetchall()

        result: list[FileOperationRow] = []
        found_target = False
        for row in rows:
            if row["checkpoint_id"] == to_checkpoint_id:
                found_target = True
            if found_target:
                break
            result.append(self._row_to_operation(row))
        return result

    def get_operations_for_checkpoint(self, thread_id: str, checkpoint_id: str) -> list[FileOperationRow]:
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT * FROM file_operations
                WHERE thread_id = ? AND checkpoint_id = ? AND status = 'applied'
                ORDER BY timestamp ASC
                """,
                (thread_id, checkpoint_id),
            )
            rows = cursor.fetchall()
        return [self._row_to_operation(row) for row in rows]

    def count_operations_for_checkpoint(self, thread_id: str, checkpoint_id: str) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT COUNT(*) FROM file_operations
                WHERE thread_id = ? AND checkpoint_id = ? AND status = 'applied'
                """,
                (thread_id, checkpoint_id),
            )
            return int(cursor.fetchone()[0])

    def mark_reverted(self, operation_ids: list[str]) -> None:
        if not operation_ids:
            return
        placeholders = ",".join("?" * len(operation_ids))
        # @@@param_sql - operation ids can originate from runtime state; keep IN-clause parameterized.
        with self._lock:
            self._conn.execute(
                f"""
                UPDATE file_operations
                SET status = 'reverted'
                WHERE id IN ({placeholders})
                """,
                operation_ids,
            )
            self._conn.commit()

    def delete_thread_operations(self, thread_id: str) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM file_operations WHERE thread_id = ?",
                (thread_id,),
            )
            self._conn.commit()
            return int(cursor.rowcount)

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS file_operations (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                checkpoint_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                operation_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                before_content TEXT,
                after_content TEXT NOT NULL,
                changes TEXT,
                status TEXT DEFAULT 'applied'
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_file_ops_thread
            ON file_operations(thread_id, timestamp)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_file_ops_checkpoint
            ON file_operations(checkpoint_id)
            """
        )
        self._conn.commit()

    def _row_to_operation(self, row: sqlite3.Row) -> FileOperationRow:
        return FileOperationRow(
            id=row["id"],
            thread_id=row["thread_id"],
            checkpoint_id=row["checkpoint_id"],
            timestamp=row["timestamp"],
            operation_type=row["operation_type"],
            file_path=row["file_path"],
            before_content=row["before_content"],
            after_content=row["after_content"],
            changes=json.loads(row["changes"]) if row["changes"] else None,
            status=row["status"],
        )
