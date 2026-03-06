"""Task CRUD — SQLite based (panel_tasks table)."""

import json
import sqlite3
import time
import uuid
from typing import Any

from backend.web.core.config import DB_PATH
from storage.providers.sqlite.connection import create_connection


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
            completed_at INTEGER DEFAULT 0,
            tags TEXT DEFAULT '[]'
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
        ("tags", "TEXT DEFAULT '[]'"),
    ]
    for col_name, col_def in _migrate_new_columns:
        try:
            conn.execute(f"ALTER TABLE panel_tasks ADD COLUMN {col_name} {col_def}")
        except sqlite3.OperationalError:
            pass  # column already exists


def _tasks_conn() -> sqlite3.Connection:
    conn = create_connection(DB_PATH, row_factory=sqlite3.Row)
    _ensure_tasks_table(conn)
    return conn


def _deserialize_row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    try:
        d["tags"] = json.loads(d.get("tags") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    return d


def list_tasks() -> list[dict[str, Any]]:
    with _tasks_conn() as conn:
        rows = conn.execute("SELECT * FROM panel_tasks ORDER BY created_at DESC").fetchall()
        return [_deserialize_row(r) for r in rows]


def get_task(task_id: str) -> dict[str, Any] | None:
    with _tasks_conn() as conn:
        row = conn.execute("SELECT * FROM panel_tasks WHERE id = ?", (task_id,)).fetchone()
        return _deserialize_row(row) if row else None


def get_highest_priority_pending_task() -> dict[str, Any] | None:
    """Return the highest-priority pending task (high > medium > low, oldest first)."""
    with _tasks_conn() as conn:
        row = conn.execute(
            "SELECT * FROM panel_tasks WHERE status = 'pending'"
            " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,"
            " created_at ASC LIMIT 1"
        ).fetchone()
        return _deserialize_row(row) if row else None


def create_task(**fields: Any) -> dict[str, Any]:
    now = int(time.time() * 1000)
    tid = uuid.uuid4().hex
    with _tasks_conn() as conn:
        conn.execute(
            "INSERT INTO panel_tasks"
            " (id,title,description,assignee_id,status,priority,progress,deadline,created_at,"
            "  thread_id,source,cron_job_id,result,started_at,completed_at,tags)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                json.dumps(fields.get("tags", [])),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM panel_tasks WHERE id = ?", (tid,)).fetchone()
        return _deserialize_row(row)


def update_task(task_id: str, **fields: Any) -> dict[str, Any] | None:
    allowed = {
        "title", "description", "assignee_id", "status", "priority", "progress", "deadline",
        "thread_id", "source", "cron_job_id", "result", "started_at", "completed_at", "tags",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "tags" in updates:
        updates["tags"] = json.dumps(updates["tags"])
    if not updates:
        with _tasks_conn() as conn:
            row = conn.execute("SELECT * FROM panel_tasks WHERE id = ?", (task_id,)).fetchone()
            return _deserialize_row(row) if row else None
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with _tasks_conn() as conn:
        conn.execute(f"UPDATE panel_tasks SET {set_clause} WHERE id = ?", (*updates.values(), task_id))
        conn.commit()
        row = conn.execute("SELECT * FROM panel_tasks WHERE id = ?", (task_id,)).fetchone()
        return _deserialize_row(row) if row else None


def delete_task(task_id: str) -> bool:
    with _tasks_conn() as conn:
        cur = conn.execute("DELETE FROM panel_tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cur.rowcount > 0


def bulk_delete_tasks(ids: list[str]) -> int:
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with _tasks_conn() as conn:
        cur = conn.execute(f"DELETE FROM panel_tasks WHERE id IN ({placeholders})", ids)
        conn.commit()
        return cur.rowcount


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
