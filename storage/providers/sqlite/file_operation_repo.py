"""SQLite repository for file_operations persistence."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from storage.providers.sqlite.kernel import connect_sqlite

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
            self._conn = connect_sqlite(db_path, row_factory=sqlite3.Row, check_same_thread=False)
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
