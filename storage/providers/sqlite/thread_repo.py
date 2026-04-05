"""SQLite thread repository."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


def _validate_thread_identity(*, is_main: bool, branch_index: int) -> None:
    if branch_index < 0:
        raise ValueError(f"branch_index must be >= 0, got {branch_index}")
    if is_main and branch_index != 0:
        raise ValueError(f"Main thread must have branch_index=0, got {branch_index}")
    if not is_main and branch_index == 0:
        raise ValueError("Child thread must have branch_index>0")


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

    def create(
        self,
        thread_id: str,
        member_id: str,
        sandbox_type: str,
        cwd: str | None = None,
        created_at: float = 0,
        **extra: Any,
    ) -> None:
        is_main = bool(extra.get("is_main", False))
        branch_index = int(extra["branch_index"])
        _validate_thread_identity(is_main=is_main, branch_index=branch_index)
        with self._lock:
            self._conn.execute(
                "INSERT INTO threads (id, member_id, sandbox_type, cwd, model, observation_provider, is_main, branch_index, created_at)"  # noqa: E501
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    thread_id,
                    member_id,
                    sandbox_type,
                    cwd,
                    extra.get("model"),
                    extra.get("observation_provider"),
                    int(is_main),
                    branch_index,
                    created_at,
                ),
            )
            self._conn.commit()

    _COLS = (
        "id",
        "member_id",
        "sandbox_type",
        "model",
        "cwd",
        "observation_provider",
        "is_main",
        "branch_index",
        "created_at",
    )
    _SELECT = ", ".join(_COLS)

    def _to_dict(self, r: tuple) -> dict[str, Any]:
        data = dict(zip(self._COLS, r))
        data["is_main"] = bool(data["is_main"])
        data["branch_index"] = int(data["branch_index"])
        return data

    def get_by_id(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(f"SELECT {self._SELECT} FROM threads WHERE id = ?", (thread_id,)).fetchone()
            return self._to_dict(row) if row else None

    def get_main_thread(self, member_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {self._SELECT} FROM threads WHERE member_id = ? AND is_main = 1",
                (member_id,),
            ).fetchone()
            return self._to_dict(row) if row else None

    def get_next_branch_index(self, member_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(branch_index), 0) FROM threads WHERE member_id = ?",
                (member_id,),
            ).fetchone()
            return int(row[0]) + 1 if row else 1

    def list_by_member(self, member_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {self._SELECT} FROM threads WHERE member_id = ? ORDER BY branch_index, created_at",
                (member_id,),
            ).fetchall()
            return [self._to_dict(r) for r in rows]

    def list_by_owner_user_id(self, owner_user_id: str) -> list[dict[str, Any]]:
        """Return all threads owned by this user (via members.owner_user_id JOIN).

        Also JOINs entities (thread_id == entity_id) for entity_name.
        """
        cols = ", ".join(f"t.{c}" for c in self._COLS)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {cols}, m.name as member_name, m.avatar as member_avatar,"
                " e.name as entity_name FROM threads t"
                " JOIN members m ON t.member_id = m.id"
                " LEFT JOIN entities e ON e.thread_id = t.id"
                " WHERE m.owner_user_id = ?"
                " ORDER BY t.is_main DESC, t.created_at",
                (owner_user_id,),
            ).fetchall()
            ncols = len(self._COLS)
            return [
                {
                    **self._to_dict(r[:ncols]),
                    "member_name": r[ncols],
                    "member_avatar": r[ncols + 1],
                    "entity_name": r[ncols + 2],
                }
                for r in rows
            ]

    def update(self, thread_id: str, **fields: Any) -> None:
        allowed = {"sandbox_type", "model", "cwd", "observation_provider", "is_main", "branch_index"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        next_is_main = bool(sets["is_main"]) if "is_main" in sets else None
        next_branch_index = int(sets["branch_index"]) if "branch_index" in sets else None
        if next_is_main is not None or next_branch_index is not None:
            current = self.get_by_id(thread_id)
            if current is None:
                raise ValueError(f"Thread {thread_id} not found")
            _validate_thread_identity(
                is_main=next_is_main if next_is_main is not None else bool(current["is_main"]),
                branch_index=next_branch_index if next_branch_index is not None else int(current["branch_index"]),
            )
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
                is_main INTEGER NOT NULL DEFAULT 0,
                branch_index INTEGER NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(threads)").fetchall()}
        if "branch_index" not in cols:
            raise RuntimeError("threads table missing branch_index; reset ~/.leon/leon.db for the new schema")
        self._conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_threads_single_main_per_member ON threads(member_id) WHERE is_main = 1"  # noqa: E501
        )
        self._conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_threads_member_branch ON threads(member_id, branch_index)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_threads_member_created ON threads(member_id, branch_index, created_at)")
        self._conn.commit()
