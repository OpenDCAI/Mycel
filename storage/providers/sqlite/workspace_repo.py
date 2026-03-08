"""SQLite repository for workspaces."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from storage.providers.sqlite.connection import create_connection


class SQLiteWorkspaceRepo:

    def __init__(self, db_path: str | Path, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        if conn is not None:
            self._conn = conn
        else:
            self._conn = create_connection(db_path)
        self._ensure_tables()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def create(self, workspace_id: str, host_path: str, name: str | None, created_at: str) -> None:
        self._conn.execute(
            "INSERT INTO workspaces(workspace_id, host_path, name, created_at) VALUES (?, ?, ?, ?)",
            (workspace_id, host_path, name, created_at),
        )
        self._conn.commit()

    def get(self, workspace_id: str) -> dict[str, Any] | None:
        self._conn.row_factory = sqlite3.Row
        row = self._conn.execute(
            "SELECT workspace_id, host_path, name, created_at FROM workspaces WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()
        self._conn.row_factory = None
        return dict(row) if row else None

    def list_all(self) -> list[dict[str, Any]]:
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(
            "SELECT workspace_id, host_path, name, created_at FROM workspaces ORDER BY created_at DESC"
        ).fetchall()
        self._conn.row_factory = None
        return [dict(r) for r in rows]

    def delete(self, workspace_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM workspaces WHERE workspace_id = ?", (workspace_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def _ensure_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_id TEXT PRIMARY KEY,
                host_path TEXT NOT NULL,
                name TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()
