"""SQLite repositories for chats, chat entities, and chat messages."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from storage.contracts import ChatMessageRow, ChatParticipantRow, ChatRow
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


class SQLiteChatParticipantRepo:
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

    def add_participant(self, chat_id: str, user_id: str, joined_at: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO chat_participants (chat_id, user_id, joined_at) VALUES (?, ?, ?)",
                (chat_id, user_id, joined_at),
            )
            self._conn.commit()

    def list_participants(self, chat_id: str) -> list[ChatParticipantRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT chat_id, user_id, joined_at, last_read_at, muted, mute_until FROM chat_participants WHERE chat_id = ?",
                (chat_id,),
            ).fetchall()
            return [
                ChatParticipantRow(
                    chat_id=r[0],
                    user_id=r[1],
                    joined_at=r[2],
                    last_read_at=r[3],
                    muted=bool(r[4]),
                    mute_until=r[5],
                )
                for r in rows
            ]

    def list_chats_for_user(self, user_id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT chat_id FROM chat_participants WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return [r[0] for r in rows]

    def is_participant_in_chat(self, chat_id: str, user_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM chat_participants WHERE chat_id = ? AND user_id = ? LIMIT 1",
                (chat_id, user_id),
            ).fetchone()
            return row is not None

    def update_last_read(self, chat_id: str, user_id: str, last_read_at: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE chat_participants SET last_read_at = ? WHERE chat_id = ? AND user_id = ?",
                (last_read_at, chat_id, user_id),
            )
            self._conn.commit()

    def update_mute(self, chat_id: str, user_id: str, muted: bool, mute_until: float | None = None) -> None:
        def _do():
            with self._lock:
                self._conn.execute(
                    "UPDATE chat_participants SET muted = ?, mute_until = ? WHERE chat_id = ? AND user_id = ?",
                    (int(muted), mute_until, chat_id, user_id),
                )
                self._conn.commit()

        _retry_on_locked(_do)

    # @@@find-chat-between — find the 1:1 chat (exactly 2 members) between two social identities.
    # Must NOT return group chats that happen to contain both.
    def find_chat_between(self, user_a: str, user_b: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT ce1.chat_id FROM chat_participants ce1"
                " JOIN chat_participants ce2 ON ce1.chat_id = ce2.chat_id"
                " WHERE ce1.user_id = ? AND ce2.user_id = ?"
                " AND (SELECT COUNT(*) FROM chat_participants ce3"
                "      WHERE ce3.chat_id = ce1.chat_id) = 2",
                (user_a, user_b),
            ).fetchone()
            return row[0] if row else None

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_participants (
                chat_id TEXT NOT NULL REFERENCES chats(id),
                user_id TEXT NOT NULL,
                joined_at REAL NOT NULL,
                last_read_at REAL,
                muted INTEGER NOT NULL DEFAULT 0,
                mute_until REAL,
                UNIQUE(chat_id, user_id)
            )
            """
        )
        # @@@entity-id-to-user-id-migration - old chat dbs still used entity_id.
        # Rename first so later index creation does not explode on missing user_id.
        try:
            self._conn.execute("ALTER TABLE chat_entities RENAME COLUMN entity_id TO user_id")
        except sqlite3.OperationalError:
            pass  # column already named user_id, or table is new
        # @@@chat-participant-migration - add muted/mute_until if table already exists
        try:
            self._conn.execute("ALTER TABLE chat_participants ADD COLUMN muted INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # column already exists
        try:
            self._conn.execute("ALTER TABLE chat_participants ADD COLUMN mute_until REAL")
        except sqlite3.OperationalError:
            pass
        # @@@chat-participant-index — speeds up find_chat_between and list_chats_for_user
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_participants_user ON chat_participants(user_id, chat_id)")
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
        import json as _json

        mentions_json = _json.dumps(row.mentioned_ids) if row.mentioned_ids else None

        def _do():
            with self._lock:
                self._conn.execute(
                    "INSERT INTO chat_messages (id, chat_id, sender_id, content, mentions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (row.id, row.chat_id, row.sender_id, row.content, mentions_json, row.created_at),
                )
                self._conn.commit()

        _retry_on_locked(_do)

    _MSG_COLS = "id, chat_id, sender_id, content, mentions, created_at"

    def _to_msg(self, r: tuple) -> ChatMessageRow:
        import json as _json

        mentions = _json.loads(r[4]) if r[4] else []
        return ChatMessageRow(id=r[0], chat_id=r[1], sender_id=r[2], content=r[3], mentioned_ids=mentions, created_at=r[5])

    def list_by_chat(
        self,
        chat_id: str,
        *,
        limit: int = 50,
        before: float | None = None,
    ) -> list[ChatMessageRow]:
        with self._lock:
            if before is not None:
                rows = self._conn.execute(
                    f"SELECT {self._MSG_COLS} FROM chat_messages WHERE chat_id = ? AND created_at < ? ORDER BY created_at DESC LIMIT ?",
                    (chat_id, before, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    f"SELECT {self._MSG_COLS} FROM chat_messages WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
                    (chat_id, limit),
                ).fetchall()
        rows.reverse()
        return [self._to_msg(r) for r in rows]

    def list_unread(self, chat_id: str, user_id: str) -> list[ChatMessageRow]:
        """Return unread messages (after last_read_at, excluding own) in chronological order."""
        with self._lock:
            cursor_row = self._conn.execute(
                "SELECT last_read_at FROM chat_participants WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ).fetchone()
            last_read = cursor_row[0] if cursor_row else None
            if last_read is None:
                rows = self._conn.execute(
                    f"SELECT {self._MSG_COLS} FROM chat_messages WHERE chat_id = ? AND sender_id != ? ORDER BY created_at ASC",
                    (chat_id, user_id),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    f"SELECT {self._MSG_COLS} FROM chat_messages"
                    " WHERE chat_id = ? AND sender_id != ? AND created_at > ?"
                    " ORDER BY created_at ASC",
                    (chat_id, user_id, last_read),
                ).fetchall()
        return [self._to_msg(r) for r in rows]

    def list_by_time_range(
        self,
        chat_id: str,
        *,
        after: float | None = None,
        before: float | None = None,
        limit: int = 100,
    ) -> list[ChatMessageRow]:
        """Return messages in a time range, chronological order."""
        with self._lock:
            clauses = ["chat_id = ?"]
            params: list = [chat_id]
            if after is not None:
                clauses.append("created_at >= ?")
                params.append(after)
            if before is not None:
                clauses.append("created_at <= ?")
                params.append(before)
            where = " AND ".join(clauses)
            params.append(limit)
            rows = self._conn.execute(
                f"SELECT {self._MSG_COLS} FROM chat_messages WHERE {where} ORDER BY created_at ASC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [self._to_msg(r) for r in rows]

    def count_unread(self, chat_id: str, user_id: str) -> int:
        with self._lock:
            cursor_row = self._conn.execute(
                "SELECT last_read_at FROM chat_participants WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ).fetchone()
            if cursor_row is None:
                return 0
            last_read = cursor_row[0]
            if last_read is None:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM chat_messages WHERE chat_id = ? AND sender_id != ?",
                    (chat_id, user_id),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM chat_messages WHERE chat_id = ? AND sender_id != ? AND created_at > ?",
                    (chat_id, user_id, last_read),
                ).fetchone()
            return int(row[0]) if row else 0

    def has_unread_mention(self, chat_id: str, user_id: str) -> bool:
        """Check if there are unread messages that @mention this user."""
        with self._lock:
            cursor_row = self._conn.execute(
                "SELECT last_read_at FROM chat_participants WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ).fetchone()
            last_read = cursor_row[0] if cursor_row else None
            # @@@mention-query — JSON LIKE is crude but sufficient for SQLite without JSON1 extension
            mention_pattern = f'%"{user_id}"%'
            if last_read is None:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM chat_messages WHERE chat_id = ? AND mentions LIKE ? AND sender_id != ?",
                    (chat_id, mention_pattern, user_id),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM chat_messages WHERE chat_id = ? AND mentions LIKE ? AND sender_id != ? AND created_at > ?",
                    (chat_id, mention_pattern, user_id, last_read),
                ).fetchone()
            return int(row[0]) > 0 if row else False

    def search(self, query: str, *, chat_id: str | None = None, limit: int = 50) -> list[ChatMessageRow]:
        with self._lock:
            if chat_id:
                rows = self._conn.execute(
                    f"SELECT {self._MSG_COLS} FROM chat_messages WHERE chat_id = ? AND content LIKE ? ORDER BY created_at ASC LIMIT ?",
                    (chat_id, f"%{query}%", limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    f"SELECT {self._MSG_COLS} FROM chat_messages WHERE content LIKE ? ORDER BY created_at ASC LIMIT ?",
                    (f"%{query}%", limit),
                ).fetchall()
        return [self._to_msg(r) for r in rows]

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL REFERENCES chats(id),
                sender_id TEXT NOT NULL,
                content TEXT NOT NULL,
                mentions TEXT,
                created_at REAL NOT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_time ON chat_messages(chat_id, created_at)")
        # @@@mentions-migration — add mentions column if table already exists
        try:
            self._conn.execute("ALTER TABLE chat_messages ADD COLUMN mentions TEXT")
        except sqlite3.OperationalError:
            pass
        # @@@sender-entity-id-to-sender-id-migration — rename columns for existing databases
        try:
            self._conn.execute("ALTER TABLE chat_messages RENAME COLUMN sender_entity_id TO sender_id")
        except sqlite3.OperationalError:
            pass  # column already named sender_id, or table is new
        try:
            self._conn.execute("ALTER TABLE chat_messages RENAME COLUMN mentioned_entity_ids TO mentions")
        except sqlite3.OperationalError:
            pass
        self._conn.commit()
