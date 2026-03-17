"""SQLite repositories for chats, chat entities, and chat messages."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from storage.contracts import ChatEntityRow, ChatMessageRow, ChatRow
from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


def _retry_on_locked(fn, max_retries=5, delay=0.2):
    """Retry a DB write operation on 'database is locked' errors."""
    for attempt in range(max_retries):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))
                continue
            raise


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
                    "INSERT INTO chats (id, title, status, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?)",
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


class SQLiteChatEntityRepo:

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

    def add_entity(self, chat_id: str, entity_id: str, joined_at: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO chat_entities (chat_id, entity_id, joined_at)"
                " VALUES (?, ?, ?)",
                (chat_id, entity_id, joined_at),
            )
            self._conn.commit()

    def list_entities(self, chat_id: str) -> list[ChatEntityRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT chat_id, entity_id, joined_at, last_read_at, muted, mute_until"
                " FROM chat_entities WHERE chat_id = ?",
                (chat_id,),
            ).fetchall()
            return [
                ChatEntityRow(
                    chat_id=r[0], entity_id=r[1], joined_at=r[2], last_read_at=r[3],
                    muted=bool(r[4]), mute_until=r[5],
                )
                for r in rows
            ]

    def list_chats_for_entity(self, entity_id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT chat_id FROM chat_entities WHERE entity_id = ?",
                (entity_id,),
            ).fetchall()
            return [r[0] for r in rows]

    def is_entity_in_chat(self, chat_id: str, entity_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM chat_entities WHERE chat_id = ? AND entity_id = ? LIMIT 1",
                (chat_id, entity_id),
            ).fetchone()
            return row is not None

    def update_last_read(self, chat_id: str, entity_id: str, last_read_at: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE chat_entities SET last_read_at = ? WHERE chat_id = ? AND entity_id = ?",
                (last_read_at, chat_id, entity_id),
            )
            self._conn.commit()

    def update_mute(self, chat_id: str, entity_id: str, muted: bool, mute_until: float | None = None) -> None:
        def _do():
            with self._lock:
                self._conn.execute(
                    "UPDATE chat_entities SET muted = ?, mute_until = ? WHERE chat_id = ? AND entity_id = ?",
                    (int(muted), mute_until, chat_id, entity_id),
                )
                self._conn.commit()
        _retry_on_locked(_do)

    # @@@find-chat-between - core uniqueness query: two entities share at most one chat
    def find_chat_between(self, entity_a: str, entity_b: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT ce1.chat_id FROM chat_entities ce1"
                " JOIN chat_entities ce2 ON ce1.chat_id = ce2.chat_id"
                " WHERE ce1.entity_id = ? AND ce2.entity_id = ?",
                (entity_a, entity_b),
            ).fetchone()
            return row[0] if row else None

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_entities (
                chat_id TEXT NOT NULL REFERENCES chats(id),
                entity_id TEXT NOT NULL REFERENCES entities(id),
                joined_at REAL NOT NULL,
                last_read_at REAL,
                muted INTEGER NOT NULL DEFAULT 0,
                mute_until REAL,
                UNIQUE(chat_id, entity_id)
            )
            """
        )
        # @@@chat-entity-migration - add muted/mute_until if table already exists
        try:
            self._conn.execute("ALTER TABLE chat_entities ADD COLUMN muted INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # column already exists
        try:
            self._conn.execute("ALTER TABLE chat_entities ADD COLUMN mute_until REAL")
        except sqlite3.OperationalError:
            pass
        self._conn.commit()


class SQLiteChatMessageRepo:

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

    def create(self, row: ChatMessageRow) -> None:
        def _do():
            with self._lock:
                self._conn.execute(
                    "INSERT INTO chat_messages (id, chat_id, sender_entity_id, content, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (row.id, row.chat_id, row.sender_entity_id, row.content, row.created_at),
                )
                self._conn.commit()
        _retry_on_locked(_do)

    def list_by_chat(
        self, chat_id: str, *, limit: int = 50, before: float | None = None,
    ) -> list[ChatMessageRow]:
        with self._lock:
            if before is not None:
                rows = self._conn.execute(
                    "SELECT id, chat_id, sender_entity_id, content, created_at"
                    " FROM chat_messages"
                    " WHERE chat_id = ? AND created_at < ?"
                    " ORDER BY created_at DESC LIMIT ?",
                    (chat_id, before, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT id, chat_id, sender_entity_id, content, created_at"
                    " FROM chat_messages"
                    " WHERE chat_id = ?"
                    " ORDER BY created_at DESC LIMIT ?",
                    (chat_id, limit),
                ).fetchall()
        rows.reverse()
        return [
            ChatMessageRow(id=r[0], chat_id=r[1], sender_entity_id=r[2], content=r[3], created_at=r[4])
            for r in rows
        ]

    def count_unread(self, chat_id: str, entity_id: str) -> int:
        with self._lock:
            cursor_row = self._conn.execute(
                "SELECT last_read_at FROM chat_entities WHERE chat_id = ? AND entity_id = ?",
                (chat_id, entity_id),
            ).fetchone()
            if cursor_row is None:
                return 0
            last_read = cursor_row[0]
            if last_read is None:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM chat_messages WHERE chat_id = ? AND sender_entity_id != ?",
                    (chat_id, entity_id),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM chat_messages WHERE chat_id = ? AND sender_entity_id != ? AND created_at > ?",
                    (chat_id, entity_id, last_read),
                ).fetchone()
            return int(row[0]) if row else 0

    def search(self, query: str, *, chat_id: str | None = None, limit: int = 50) -> list[ChatMessageRow]:
        with self._lock:
            if chat_id:
                rows = self._conn.execute(
                    "SELECT id, chat_id, sender_entity_id, content, created_at"
                    " FROM chat_messages"
                    " WHERE chat_id = ? AND content LIKE ?"
                    " ORDER BY created_at ASC LIMIT ?",
                    (chat_id, f"%{query}%", limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT id, chat_id, sender_entity_id, content, created_at"
                    " FROM chat_messages"
                    " WHERE content LIKE ?"
                    " ORDER BY created_at ASC LIMIT ?",
                    (f"%{query}%", limit),
                ).fetchall()
        return [
            ChatMessageRow(id=r[0], chat_id=r[1], sender_entity_id=r[2], content=r[3], created_at=r[4])
            for r in rows
        ]

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL REFERENCES chats(id),
                sender_entity_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_time ON chat_messages(chat_id, created_at)"
        )
        self._conn.commit()
