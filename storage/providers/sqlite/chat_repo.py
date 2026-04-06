"""SQLite repository for chats."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from storage.contracts import ChatRow
from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path
from storage.providers.sqlite.kernel import retry_on_locked as _retry_on_locked


class SQLiteChatRepo:
    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            if db_path is None:
                db_path = resolve_role_db_path(SQLiteDBRole.CHAT)
            self._conn = create_connection(db_path)
        self._ensure_table()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def create(self, row: ChatRow) -> None:
        def _do():
            with self._lock:
                self._conn.execute(
                    "INSERT INTO chats (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (row.id, row.title, row.status, row.created_at, row.updated_at),
                )
                self._conn.commit()

        _retry_on_locked(_do)

    def get_by_id(self, chat_id: str) -> ChatRow | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
            return self._to_row(row) if row else None

    def delete(self, chat_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            self._conn.commit()

    def _to_row(self, r: tuple) -> ChatRow:
        return ChatRow(id=r[0], title=r[1], status=r[2], created_at=r[3], updated_at=r[4])

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT,
                status TEXT DEFAULT 'active',
                created_at REAL NOT NULL,
                updated_at REAL
            )
            """
        )
        self._conn.commit()
