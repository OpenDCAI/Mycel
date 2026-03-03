"""Cron Jobs CRUD — SQLite based (cron_jobs table)."""

import sqlite3
import time
from typing import Any

from backend.web.core.config import DB_PATH


def _ensure_cron_jobs_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
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


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _ensure_cron_jobs_table(conn)
    return conn


def list_cron_jobs() -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM cron_jobs ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_cron_job(job_id: str) -> dict[str, Any] | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def create_cron_job(*, name: str, cron_expression: str, **fields: Any) -> dict[str, Any]:
    if not name or not name.strip():
        raise ValueError("name must not be empty")
    if not cron_expression or not cron_expression.strip():
        raise ValueError("cron_expression must not be empty")

    now = int(time.time() * 1000)
    job_id = str(now)
    with _conn() as c:
        c.execute(
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
        c.commit()
        row = c.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row)


def update_cron_job(job_id: str, **fields: Any) -> dict[str, Any] | None:
    allowed = {
        "name", "description", "cron_expression", "task_template",
        "enabled", "last_run_at", "next_run_at",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        with _conn() as c:
            row = c.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with _conn() as c:
        c.execute(
            f"UPDATE cron_jobs SET {set_clause} WHERE id = ?",
            (*updates.values(), job_id),
        )
        c.commit()
        row = c.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def delete_cron_job(job_id: str) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
        c.commit()
        return cur.rowcount > 0
