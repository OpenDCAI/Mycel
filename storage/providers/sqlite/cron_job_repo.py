"""SQLite repo for cron_jobs records."""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from backend.web.core.config import DB_PATH
from storage.providers.sqlite.connection import create_connection


class SQLiteCronJobRepo:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else DB_PATH
        self._conn = create_connection(self._db_path, row_factory=sqlite3.Row)
        self._ensure_table()

    def close(self) -> None:
        self._conn.close()

    def _ensure_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cron_jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                cron_expression TEXT NOT NULL,
                task_template TEXT DEFAULT '{}',
                enabled INTEGER DEFAULT 1,
                last_run_at INTEGER DEFAULT 0,
                next_run_at INTEGER DEFAULT 0,
                created_at INTEGER NOT NULL
            )
        """)
        self._conn.commit()

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM cron_jobs ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def get(self, job_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def create(self, *, name: str, cron_expression: str, **fields: Any) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        now = int(time.time() * 1000)
        self._conn.execute(
            "INSERT INTO cron_jobs"
            " (id, name, description, cron_expression, task_template,"
            "  enabled, last_run_at, next_run_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                name,
                fields.get("description", ""),
                cron_expression,
                fields.get("task_template", "{}"),
                fields.get("enabled", 1),
                fields.get("last_run_at", 0),
                fields.get("next_run_at", 0),
                now,
            ),
        )
        self._conn.commit()
        return self.get(job_id) or {}

    def update(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "name", "description", "cron_expression", "task_template",
            "enabled", "last_run_at", "next_run_at",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get(job_id)
        set_clause = ", ".join(f"{key} = ?" for key in updates)
        self._conn.execute(
            f"UPDATE cron_jobs SET {set_clause} WHERE id = ?",
            (*updates.values(), job_id),
        )
        self._conn.commit()
        return self.get(job_id)

    def delete(self, job_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
        self._conn.commit()
        return cur.rowcount > 0
