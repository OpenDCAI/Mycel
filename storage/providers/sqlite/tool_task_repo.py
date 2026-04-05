"""SQLite repo for thread-scoped tool tasks."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.tools.task.types import Task, TaskStatus


class SQLiteToolTaskRepo:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    thread_id  TEXT NOT NULL,
                    task_id    TEXT NOT NULL,
                    subject    TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status     TEXT NOT NULL DEFAULT 'pending',
                    active_form TEXT,
                    owner      TEXT,
                    blocks     TEXT NOT NULL DEFAULT '[]',
                    blocked_by TEXT NOT NULL DEFAULT '[]',
                    metadata   TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (thread_id, task_id)
                )
            """)
            conn.commit()

    def next_id(self, thread_id: str) -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM tasks WHERE thread_id = ?", (thread_id,)).fetchone()
            return str((row[0] or 0) + 1)

    def get(self, thread_id: str, task_id: str) -> Task | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE thread_id = ? AND task_id = ?",
                (thread_id, task_id),
            ).fetchone()
        return self._row_to_task(row) if row else None

    def list_all(self, thread_id: str) -> list[Task]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM tasks WHERE thread_id = ? ORDER BY task_id", (thread_id,)).fetchall()
        return [self._row_to_task(row) for row in rows]

    def insert(self, thread_id: str, task: Task) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO tasks
                   (thread_id, task_id, subject, description, status,
                    active_form, owner, blocks, blocked_by, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    thread_id,
                    task.id,
                    task.subject,
                    task.description,
                    task.status.value,
                    task.active_form,
                    task.owner,
                    json.dumps(task.blocks),
                    json.dumps(task.blocked_by),
                    json.dumps(task.metadata),
                ),
            )
            conn.commit()

    def update(self, thread_id: str, task: Task) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE tasks SET
                   subject=?, description=?, status=?, active_form=?,
                   owner=?, blocks=?, blocked_by=?, metadata=?
                   WHERE thread_id=? AND task_id=?""",
                (
                    task.subject,
                    task.description,
                    task.status.value,
                    task.active_form,
                    task.owner,
                    json.dumps(task.blocks),
                    json.dumps(task.blocked_by),
                    json.dumps(task.metadata),
                    thread_id,
                    task.id,
                ),
            )
            conn.commit()

    def delete(self, thread_id: str, task_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM tasks WHERE thread_id = ? AND task_id = ?", (thread_id, task_id))
            conn.commit()

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task(
            id=row["task_id"],
            subject=row["subject"],
            description=row["description"],
            status=TaskStatus(row["status"]),
            active_form=row["active_form"],
            owner=row["owner"],
            blocks=json.loads(row["blocks"]),
            blocked_by=json.loads(row["blocked_by"]),
            metadata=json.loads(row["metadata"]),
        )
