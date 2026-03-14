"""SQLite repositories for conversations, conversation members, and messages."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from storage.contracts import ConversationMemberRow, ConversationMessageRow, ConversationRow
from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


class SQLiteConversationRepo:

    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            if db_path is None:
                db_path = resolve_role_db_path(SQLiteDBRole.CONVERSATION)
            self._conn = create_connection(db_path)
        self._ensure_table()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def create(self, row: ConversationRow) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO conversations (id, title, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (row.id, row.title, row.status, row.created_at, row.updated_at),
            )
            self._conn.commit()

    def get_by_id(self, conversation_id: str) -> ConversationRow | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            return self._to_row(row) if row else None

    def list_by_member(self, member_id: str) -> list[ConversationRow]:
        """List conversations where this member is a participant."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT c.* FROM conversations c"
                " JOIN conversation_members cm ON c.id = cm.conversation_id"
                " WHERE cm.member_id = ? ORDER BY c.updated_at DESC NULLS LAST, c.created_at DESC",
                (member_id,),
            ).fetchall()
            return [self._to_row(r) for r in rows]

    def update_status(self, conversation_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE conversations SET status = ? WHERE id = ?",
                (status, conversation_id),
            )
            self._conn.commit()

    def _to_row(self, r: tuple) -> ConversationRow:
        return ConversationRow(
            id=r[0], title=r[1],
            status=r[2], created_at=r[3], updated_at=r[4],
        )

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at REAL NOT NULL,
                updated_at REAL
            )
            """
        )
        self._conn.commit()


class SQLiteConversationMemberRepo:

    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            if db_path is None:
                db_path = resolve_role_db_path(SQLiteDBRole.CONVERSATION)
            self._conn = create_connection(db_path)
        self._ensure_table()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def add_member(self, conversation_id: str, member_id: str, joined_at: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO conversation_members (conversation_id, member_id, joined_at)"
                " VALUES (?, ?, ?)",
                (conversation_id, member_id, joined_at),
            )
            self._conn.commit()

    def remove_member(self, conversation_id: str, member_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM conversation_members WHERE conversation_id = ? AND member_id = ?",
                (conversation_id, member_id),
            )
            self._conn.commit()

    def list_members(self, conversation_id: str) -> list[ConversationMemberRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT conversation_id, member_id, joined_at, last_read_at"
                " FROM conversation_members WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
            return [ConversationMemberRow(conversation_id=r[0], member_id=r[1], joined_at=r[2], last_read_at=r[3]) for r in rows]

    def list_conversations_for_member(self, member_id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT conversation_id FROM conversation_members WHERE member_id = ?",
                (member_id,),
            ).fetchall()
            return [r[0] for r in rows]

    def is_member(self, conversation_id: str, member_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM conversation_members WHERE conversation_id = ? AND member_id = ? LIMIT 1",
                (conversation_id, member_id),
            ).fetchone()
            return row is not None

    def update_last_read(self, conversation_id: str, member_id: str, last_read_at: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE conversation_members SET last_read_at = ? WHERE conversation_id = ? AND member_id = ?",
                (last_read_at, conversation_id, member_id),
            )
            self._conn.commit()

    def get_last_read_at(self, conversation_id: str, member_id: str) -> float | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT last_read_at FROM conversation_members WHERE conversation_id = ? AND member_id = ?",
                (conversation_id, member_id),
            ).fetchone()
            return row[0] if row else None

    def list_all_edges(self) -> list[tuple[str, str, int]]:
        """Self-join to get (source, target, weight) edges between co-members.

        Weight = total messages across all shared conversations.
        Falls back to conversation count if no messages exist.
        """
        with self._lock:
            rows = self._conn.execute(
                # @@@edge-weight-messages — count messages in shared conversations
                "SELECT cm1.member_id, cm2.member_id,"
                "  COALESCE(SUM(msg_counts.cnt), COUNT(DISTINCT cm1.conversation_id))"
                " FROM conversation_members cm1"
                " JOIN conversation_members cm2"
                "   ON cm1.conversation_id = cm2.conversation_id"
                "   AND cm1.member_id < cm2.member_id"
                " LEFT JOIN ("
                "   SELECT conversation_id, COUNT(*) AS cnt"
                "   FROM conversation_messages GROUP BY conversation_id"
                " ) msg_counts ON msg_counts.conversation_id = cm1.conversation_id"
                " GROUP BY cm1.member_id, cm2.member_id",
            ).fetchall()
            return [(r[0], r[1], r[2]) for r in rows]

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_members (
                conversation_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                joined_at REAL NOT NULL,
                last_read_at REAL,
                PRIMARY KEY (conversation_id, member_id)
            )
            """
        )
        self._conn.commit()


class SQLiteConversationMessageRepo:

    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            if db_path is None:
                db_path = resolve_role_db_path(SQLiteDBRole.CONVERSATION)
            self._conn = create_connection(db_path)
        self._ensure_table()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def create(self, row: ConversationMessageRow) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO conversation_messages (id, conversation_id, sender_id, content, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (row.id, row.conversation_id, row.sender_id, row.content, row.created_at),
            )
            self._conn.commit()

    def list_by_conversation(
        self, conversation_id: str, *, limit: int = 50, before: float | None = None,
    ) -> list[ConversationMessageRow]:
        with self._lock:
            if before is not None:
                rows = self._conn.execute(
                    "SELECT id, conversation_id, sender_id, content, created_at"
                    " FROM conversation_messages"
                    " WHERE conversation_id = ? AND created_at < ?"
                    " ORDER BY created_at DESC LIMIT ?",
                    (conversation_id, before, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT id, conversation_id, sender_id, content, created_at"
                    " FROM conversation_messages"
                    " WHERE conversation_id = ?"
                    " ORDER BY created_at DESC LIMIT ?",
                    (conversation_id, limit),
                ).fetchall()
        # Return in chronological order (query was DESC for LIMIT, reverse back)
        rows.reverse()
        return [
            ConversationMessageRow(id=r[0], conversation_id=r[1], sender_id=r[2], content=r[3], created_at=r[4])
            for r in rows
        ]

    def search_in_conversation(
        self, conversation_id: str, query: str, *, limit: int = 50,
    ) -> list[ConversationMessageRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, conversation_id, sender_id, content, created_at"
                " FROM conversation_messages"
                " WHERE conversation_id = ? AND content LIKE ?"
                " ORDER BY created_at ASC LIMIT ?",
                (conversation_id, f"%{query}%", limit),
            ).fetchall()
        return [
            ConversationMessageRow(id=r[0], conversation_id=r[1], sender_id=r[2], content=r[3], created_at=r[4])
            for r in rows
        ]

    def count_unread(self, conversation_id: str, member_id: str) -> int:
        """Count messages after this member's last_read_at in the conversation."""
        with self._lock:
            # Get last_read_at from conversation_members
            cursor_row = self._conn.execute(
                "SELECT last_read_at FROM conversation_members WHERE conversation_id = ? AND member_id = ?",
                (conversation_id, member_id),
            ).fetchone()
            if cursor_row is None:
                return 0
            last_read = cursor_row[0]
            if last_read is None:
                # Never read — all messages except own are unread
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = ? AND sender_id != ?",
                    (conversation_id, member_id),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = ? AND sender_id != ? AND created_at > ?",
                    (conversation_id, member_id, last_read),
                ).fetchone()
            return int(row[0]) if row else 0

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conv_msg_conv ON conversation_messages (conversation_id, created_at)"
        )
        self._conn.commit()
