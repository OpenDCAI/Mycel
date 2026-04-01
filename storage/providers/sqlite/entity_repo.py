"""SQLite entity repository."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from storage.contracts import EntityRow
from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


class SQLiteEntityRepo:
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

    def create(self, row: EntityRow) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO entities (id, type, member_id, name, avatar, thread_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (row.id, row.type, row.member_id, row.name, row.avatar, row.thread_id, row.created_at),
            )
            self._conn.commit()

    def get_by_id(self, entity_id: str) -> EntityRow | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
            return self._to_row(row) if row else None

    def get_by_member_id(self, member_id: str) -> list[EntityRow]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM entities WHERE member_id = ?", (member_id,)).fetchall()
            return [self._to_row(r) for r in rows]

    def get_by_thread_id(self, thread_id: str) -> EntityRow | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM entities WHERE thread_id = ?", (thread_id,)).fetchone()
            return self._to_row(row) if row else None

    def list_all(self) -> list[EntityRow]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM entities ORDER BY created_at").fetchall()
            return [self._to_row(r) for r in rows]

    def list_by_type(self, entity_type: str) -> list[EntityRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE type = ? ORDER BY created_at",
                (entity_type,),
            ).fetchall()
            return [self._to_row(r) for r in rows]

    def update(self, entity_id: str, **fields: str | None) -> None:
        allowed = {"name", "avatar", "thread_id"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with self._lock:
            self._conn.execute(
                f"UPDATE entities SET {set_clause} WHERE id = ?",
                (*updates.values(), entity_id),
            )
            self._conn.commit()

    def delete(self, entity_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            self._conn.commit()

    def _to_row(self, r: tuple) -> EntityRow:
        return EntityRow(
            id=r[0],
            type=r[1],
            member_id=r[2],
            name=r[3],
            avatar=r[4],
            thread_id=r[5],
            created_at=r[6],
        )

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                member_id TEXT NOT NULL,
                name TEXT NOT NULL,
                avatar TEXT,
                thread_id TEXT UNIQUE,
                created_at REAL NOT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_member ON entities(member_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_thread ON entities(thread_id)")
        self._conn.commit()
