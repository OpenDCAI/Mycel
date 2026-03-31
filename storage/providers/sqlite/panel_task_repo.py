"""SQLite repo for panel task board records."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from backend.web.core.config import DB_PATH
from storage.providers.sqlite.connection import create_connection

TASK_STATUS_ALIASES = {
    "done": "completed",
}


class SQLitePanelTaskRepo:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else DB_PATH
        self._conn = create_connection(self._db_path, row_factory=sqlite3.Row)
        self._ensure_table()

    def close(self) -> None:
        self._conn.close()

    def _ensure_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS panel_tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                assignee_id TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                priority TEXT DEFAULT 'medium',
                progress INTEGER DEFAULT 0,
                deadline TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                thread_id TEXT DEFAULT '',
                source TEXT DEFAULT 'manual',
                cron_job_id TEXT DEFAULT '',
                result TEXT DEFAULT '',
                started_at INTEGER DEFAULT 0,
                completed_at INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]'
            )
        """)
        for col_name, col_def in [
            ("thread_id", "TEXT DEFAULT ''"),
            ("source", "TEXT DEFAULT 'manual'"),
            ("cron_job_id", "TEXT DEFAULT ''"),
            ("result", "TEXT DEFAULT ''"),
            ("started_at", "INTEGER DEFAULT 0"),
            ("completed_at", "INTEGER DEFAULT 0"),
            ("tags", "TEXT DEFAULT '[]'"),
        ]:
            try:
                self._conn.execute(f"ALTER TABLE panel_tasks ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass
        # @@@task-status-canonicalize - old local boards wrote `done`; normalize persisted rows
        # once here so the repo only emits the canonical frontend/backend task contract.
        self._conn.execute(
            "UPDATE panel_tasks SET status = ? WHERE status = ?",
            ("completed", "done"),
        )
        self._conn.commit()

    def _deserialize(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        data["status"] = TASK_STATUS_ALIASES.get(data.get("status"), data.get("status"))
        try:
            data["tags"] = json.loads(data.get("tags") or "[]")
        except (json.JSONDecodeError, TypeError):
            data["tags"] = []
        return data

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM panel_tasks ORDER BY created_at DESC").fetchall()
        return [self._deserialize(row) for row in rows if row is not None]

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM panel_tasks WHERE id = ?", (task_id,)).fetchone()
        return self._deserialize(row)

    def get_highest_priority_pending(self) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM panel_tasks WHERE status = 'pending'"
            " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,"
            " created_at ASC LIMIT 1"
        ).fetchone()
        return self._deserialize(row)

    def create(self, **fields: Any) -> dict[str, Any]:
        task_id = uuid.uuid4().hex
        now = int(time.time() * 1000)
        self._conn.execute(
            "INSERT INTO panel_tasks"
            " (id,title,description,assignee_id,status,priority,progress,deadline,created_at,"
            "  thread_id,source,cron_job_id,result,started_at,completed_at,tags)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                task_id,
                fields.get("title", "新任务"),
                fields.get("description", ""),
                fields.get("assignee_id", ""),
                "pending",
                fields.get("priority", "medium"),
                0,
                fields.get("deadline", ""),
                now,
                fields.get("thread_id", ""),
                fields.get("source", "manual"),
                fields.get("cron_job_id", ""),
                fields.get("result", ""),
                fields.get("started_at", 0),
                fields.get("completed_at", 0),
                json.dumps(fields.get("tags", [])),
            ),
        )
        self._conn.commit()
        return self.get(task_id) or {}

    def update(self, task_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "title", "description", "assignee_id", "status", "priority", "progress", "deadline",
            "thread_id", "source", "cron_job_id", "result", "started_at", "completed_at", "tags",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "tags" in updates:
            updates["tags"] = json.dumps(updates["tags"])
        if not updates:
            return self.get(task_id)
        set_clause = ", ".join(f"{key} = ?" for key in updates)
        self._conn.execute(f"UPDATE panel_tasks SET {set_clause} WHERE id = ?", (*updates.values(), task_id))
        self._conn.commit()
        return self.get(task_id)

    def delete(self, task_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM panel_tasks WHERE id = ?", (task_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def bulk_delete(self, ids: list[str]) -> int:
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        cur = self._conn.execute(f"DELETE FROM panel_tasks WHERE id IN ({placeholders})", ids)
        self._conn.commit()
        return cur.rowcount

    def bulk_update_status(self, ids: list[str], status: str) -> int:
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        progress_update = ""
        if status == "completed":
            progress_update = ", progress = 100"
        elif status == "pending":
            progress_update = ", progress = 0"
        cur = self._conn.execute(
            f"UPDATE panel_tasks SET status = ?{progress_update} WHERE id IN ({placeholders})",
            (status, *ids),
        )
        self._conn.commit()
        return cur.rowcount
