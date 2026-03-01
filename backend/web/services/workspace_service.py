"""Workspace management service.

A workspace is a named directory on the host machine that can be shared across
multiple threads. Each thread can have at most one workspace_id; multiple threads
can reference the same workspace.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.web.core.config import DB_PATH


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workspaces (
            workspace_id TEXT PRIMARY KEY,
            host_path TEXT NOT NULL,
            name TEXT,
            created_at TEXT NOT NULL
        )
        """
    )


def create_workspace(host_path: str, name: str | None = None) -> dict[str, Any]:
    host = Path(host_path).expanduser().resolve()
    if not host.exists():
        raise ValueError(f"Workspace host_path does not exist: {host}")
    workspace_id = str(uuid.uuid4())
    now = _now_utc()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        _ensure_table(conn)
        conn.execute(
            "INSERT INTO workspaces(workspace_id, host_path, name, created_at) VALUES (?, ?, ?, ?)",
            (workspace_id, str(host), name, now),
        )
        conn.commit()
    return {"workspace_id": workspace_id, "host_path": str(host), "name": name, "created_at": now}


def get_workspace(workspace_id: str) -> dict[str, Any] | None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_table(conn)
        row = conn.execute(
            "SELECT workspace_id, host_path, name, created_at FROM workspaces WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()
    return dict(row) if row else None


def list_workspaces() -> list[dict[str, Any]]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_table(conn)
        rows = conn.execute(
            "SELECT workspace_id, host_path, name, created_at FROM workspaces ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_workspace(workspace_id: str) -> bool:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        _ensure_table(conn)
        cur = conn.execute("DELETE FROM workspaces WHERE workspace_id = ?", (workspace_id,))
        conn.commit()
    return cur.rowcount > 0
