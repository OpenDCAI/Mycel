"""Task CRUD — SQLite based (panel_tasks table)."""

import sqlite3
import time
from typing import Any

from backend.web.core.config import DB_PATH


def _ensure_tasks_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
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
            completed_at INTEGER DEFAULT 0
        )
    """)
    # Migrate existing databases that lack the new columns.
    _migrate_new_columns = [
        ("thread_id", "TEXT DEFAULT ''"),
        ("source", "TEXT DEFAULT 'manual'"),
        ("cron_job_id", "TEXT DEFAULT ''"),
        ("result", "TEXT DEFAULT ''"),
        ("started_at", "INTEGER DEFAULT 0"),
        ("completed_at", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_def in _migrate_new_columns:
        try:
            conn.execute(f"ALTER TABLE panel_tasks ADD COLUMN {col_name} {col_def}")
        except sqlite3.OperationalError:
            pass  # column already exists


def _tasks_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _ensure_tasks_table(conn)
    return conn


def list_tasks() -> list[dict[str, Any]]:
    with _tasks_conn() as conn:
        rows = conn.execute("SELECT * FROM panel_tasks ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def create_task(**fields: Any) -> dict[str, Any]:
    now = int(time.time() * 1000)
    tid = str(now)
    with _tasks_conn() as conn:
        conn.execute(
            "INSERT INTO panel_tasks"
            " (id,title,description,assignee_id,status,priority,progress,deadline,created_at,"
            "  thread_id,source,cron_job_id,result,started_at,completed_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                tid,
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
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM panel_tasks WHERE id = ?", (tid,)).fetchone()
        return dict(row)


def update_task(task_id: str, **fields: Any) -> dict[str, Any] | None:
    allowed = {
        "title", "description", "assignee_id", "status", "priority", "progress", "deadline",
        "thread_id", "source", "cron_job_id", "result", "started_at", "completed_at",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        with _tasks_conn() as conn:
            row = conn.execute("SELECT * FROM panel_tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row) if row else None
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with _tasks_conn() as conn:
        conn.execute(f"UPDATE panel_tasks SET {set_clause} WHERE id = ?", (*updates.values(), task_id))
        conn.commit()
        row = conn.execute("SELECT * FROM panel_tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def delete_task(task_id: str) -> bool:
    with _tasks_conn() as conn:
        cur = conn.execute("DELETE FROM panel_tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cur.rowcount > 0


def bulk_update_task_status(ids: list[str], status: str) -> int:
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    progress_update = ""
    if status == "completed":
        progress_update = ", progress = 100"
    elif status == "pending":
        progress_update = ", progress = 0"
    with _tasks_conn() as conn:
        cur = conn.execute(
            f"UPDATE panel_tasks SET status = ?{progress_update} WHERE id IN ({placeholders})",
            (status, *ids),
        )
        conn.commit()
        return cur.rowcount
