"""SQLite repository for members and accounts."""

from __future__ import annotations

import secrets
import sqlite3
import string
import threading
from pathlib import Path
from typing import Any

from storage.contracts import MemberRow, MemberType
from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path

_ID_ALPHABET = string.ascii_letters + string.digits


def generate_member_id() -> str:
    """Generate member ID: m_{12 random alphanumeric chars}."""
    return "m_" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(12))


class SQLiteMemberRepo:
    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            if db_path is None:
                db_path = resolve_role_db_path(SQLiteDBRole.MAIN)
            self._conn = create_connection(db_path)
        self._ensure_table()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def create(self, row: MemberRow) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO members (id, name, type, avatar, description, config_dir, owner_user_id, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.id,
                    row.name,
                    row.type.value,
                    row.avatar,
                    row.description,
                    row.config_dir,
                    row.owner_user_id,
                    row.created_at,
                    row.updated_at,
                ),
            )
            self._conn.commit()

    def get_by_id(self, member_id: str) -> MemberRow | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
            return self._to_row(row) if row else None

    def get_by_name(self, name: str) -> MemberRow | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM members WHERE name = ?", (name,)).fetchone()
            return self._to_row(row) if row else None

    def get_by_email(self, email: str) -> MemberRow | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM members WHERE email = ?", (email,)).fetchone()
            return self._to_row(row) if row else None

    def get_by_mycel_id(self, mycel_id: int) -> MemberRow | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM members WHERE mycel_id = ?", (mycel_id,)).fetchone()
            return self._to_row(row) if row else None

    def list_all(self) -> list[MemberRow]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM members ORDER BY created_at").fetchall()
            return [self._to_row(r) for r in rows]

    def list_by_type(self, member_type: str) -> list[MemberRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM members WHERE type = ? ORDER BY created_at",
                (member_type,),
            ).fetchall()
            return [self._to_row(r) for r in rows]

    def list_by_owner_user_id(self, owner_user_id: str) -> list[MemberRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM members WHERE owner_user_id = ? ORDER BY created_at",
                (owner_user_id,),
            ).fetchall()
            return [self._to_row(r) for r in rows]

    def update(self, member_id: str, **fields: Any) -> None:
        allowed = {"name", "avatar", "description", "config_dir", "owner_user_id", "main_thread_id", "updated_at"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with self._lock:
            self._conn.execute(
                f"UPDATE members SET {set_clause} WHERE id = ?",
                (*updates.values(), member_id),
            )
            self._conn.commit()

    def increment_thread_seq(self, member_id: str) -> int:
        """Atomically increment next_thread_seq and return the new value."""
        with self._lock:
            self._conn.execute(
                "UPDATE members SET next_thread_seq = next_thread_seq + 1 WHERE id = ?",
                (member_id,),
            )
            row = self._conn.execute(
                "SELECT next_thread_seq FROM members WHERE id = ?",
                (member_id,),
            ).fetchone()
            self._conn.commit()
            if not row:
                raise ValueError(f"Member {member_id} not found")
            return row[0]

    def delete(self, member_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
            self._conn.commit()

    def _to_row(self, r: tuple) -> MemberRow:
        return MemberRow(
            id=r[0],
            name=r[1],
            type=MemberType(r[2]),
            avatar=r[3],
            description=r[4],
            config_dir=r[5],
            owner_user_id=r[6],
            created_at=r[7],
            updated_at=r[8],
            next_thread_seq=r[9] if len(r) > 9 else 0,
            main_thread_id=r[10] if len(r) > 10 else None,
        )

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS members (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                avatar TEXT,
                description TEXT,
                config_dir TEXT,
                owner_user_id TEXT,
                created_at REAL NOT NULL,
                updated_at REAL,
                next_thread_seq INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(members)").fetchall()}
        if "owner_user_id" not in cols:
            raise RuntimeError("members table missing owner_user_id; reset ~/.leon/leon.db for the new schema")
        if "main_thread_id" not in cols:
            self._conn.execute("ALTER TABLE members ADD COLUMN main_thread_id TEXT")
        self._conn.commit()


