"""SQLite repository for message queue persistence."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from storage.contracts import QueueItem
from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite, resolve_role_db_path


class SQLiteQueueRepo:
    """Message queue backed by SQLite.

    Thread-safe: all connection access is serialized via a lock.
    """

    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
            self._db_path = str(db_path) if db_path else ""
        else:
            if db_path is None:
                db_path = resolve_role_db_path(SQLiteDBRole.QUEUE)
            self._db_path = str(db_path)
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = connect_sqlite(db_path, check_same_thread=False)
        self._ensure_table()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def enqueue(
        self,
        thread_id: str,
        content: str,
        notification_type: str = "steer",
        source: str | None = None,
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO message_queue (thread_id, content, notification_type, source, sender_id, sender_name)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (thread_id, content, notification_type, source, sender_id, sender_name),
            )
            self._conn.commit()

    def dequeue(self, thread_id: str) -> QueueItem | None:
        with self._lock:
            has_row = self._conn.execute(
                "SELECT 1 FROM message_queue WHERE thread_id = ? LIMIT 1",
                (thread_id,),
            ).fetchone()
            if has_row is None:
                return None
            row = self._conn.execute(
                "DELETE FROM message_queue "
                "WHERE id = (SELECT MIN(id) FROM message_queue WHERE thread_id = ?) "
                "RETURNING content, notification_type, source, sender_id, sender_name",
                (thread_id,),
            ).fetchone()
            self._conn.commit()
            return QueueItem(content=row[0], notification_type=row[1], source=row[2], sender_id=row[3], sender_name=row[4]) if row else None

    def drain_all(self, thread_id: str) -> list[QueueItem]:
        with self._lock:
            has_row = self._conn.execute(
                "SELECT 1 FROM message_queue WHERE thread_id = ? LIMIT 1",
                (thread_id,),
            ).fetchone()
            if has_row is None:
                return []
            rows = self._conn.execute(
                "DELETE FROM message_queue WHERE thread_id = ? RETURNING content, notification_type, id, source, sender_id, sender_name",
                (thread_id,),
            ).fetchall()
            self._conn.commit()
        return [
            QueueItem(content=r[0], notification_type=r[1], source=r[3], sender_id=r[4], sender_name=r[5])
            for r in sorted(rows, key=lambda r: r[2])
        ]

    def peek(self, thread_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM message_queue WHERE thread_id = ? LIMIT 1",
                (thread_id,),
            ).fetchone()
            return row is not None

    def list_queue(self, thread_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, content, notification_type, created_at FROM message_queue WHERE thread_id = ? ORDER BY id",
                (thread_id,),
            ).fetchall()
            return [{"id": r[0], "content": r[1], "notification_type": r[2], "created_at": r[3]} for r in rows]

    def clear_queue(self, thread_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM message_queue WHERE thread_id = ?",
                (thread_id,),
            )
            self._conn.commit()

    def count(self, thread_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM message_queue WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            return int(row[0]) if row else 0

    def _ensure_table(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS message_queue ("
            "  id                INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  thread_id         TEXT NOT NULL,"
            "  content           TEXT NOT NULL,"
            "  notification_type TEXT NOT NULL DEFAULT 'steer',"
            "  source            TEXT,"
            "  sender_id         TEXT,"
            "  sender_name       TEXT,"
            "  created_at        TEXT DEFAULT (datetime('now'))"
            ")"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_mq_thread ON message_queue (thread_id, id)")
        self._conn.commit()
