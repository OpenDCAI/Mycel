"""SQLite thread repository."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


class SQLiteThreadRepo:
    """Thread metadata store. Replaces ThreadConfigRepo.

    DB role: MAIN (same DB as members, entities, checkpoints).
    """

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

    def create(self, thread_id: str, member_id: str, sandbox_type: str,
               cwd: str | None = None, created_at: float = 0, **extra: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO threads (id, member_id, sandbox_type, cwd, model, observation_provider, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (thread_id, member_id, sandbox_type, cwd,
                 extra.get("model"), extra.get("observation_provider"), created_at),
            )
            self._conn.commit()

    _COLS = ("id", "member_id", "sandbox_type", "model", "cwd", "observation_provider", "created_at")
    _SELECT = ", ".join(_COLS)

    def _to_dict(self, r: tuple) -> dict[str, Any]:
        return dict(zip(self._COLS, r))

    def get_by_id(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(f"SELECT {self._SELECT} FROM threads WHERE id = ?", (thread_id,)).fetchone()
            return self._to_dict(row) if row else None

    def list_by_member(self, member_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {self._SELECT} FROM threads WHERE member_id = ? ORDER BY created_at", (member_id,),
            ).fetchall()
            return [self._to_dict(r) for r in rows]

    def list_by_owner(self, owner_member_id: str) -> list[dict[str, Any]]:
        """Return all threads owned by this member (via members.owner_id JOIN)."""
        cols = ", ".join(f"t.{c}" for c in self._COLS)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {cols}, m.name as member_name, m.avatar as member_avatar FROM threads t"
                " JOIN members m ON t.member_id = m.id"
                " WHERE m.owner_id = ?"
                " ORDER BY t.created_at",
                (owner_member_id,),
            ).fetchall()
            ncols = len(self._COLS)
            return [{**self._to_dict(r[:ncols]), "member_name": r[ncols], "member_avatar": r[ncols + 1]} for r in rows]

    def update(self, thread_id: str, **fields: Any) -> None:
        allowed = {"sandbox_type", "model", "cwd", "observation_provider"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        sql = "UPDATE threads SET " + ", ".join(f"{k} = ?" for k in sets) + " WHERE id = ?"
        with self._lock:
            self._conn.execute(sql, [*sets.values(), thread_id])
            self._conn.commit()

    def delete(self, thread_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
            self._conn.commit()

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                member_id TEXT NOT NULL,
                sandbox_type TEXT DEFAULT 'local',
                model TEXT,
                cwd TEXT,
                observation_provider TEXT,
                agent TEXT,
                created_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()
