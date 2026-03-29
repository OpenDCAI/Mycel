"""SQLite-backed scheduled task storage."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Any

from croniter import croniter

from backend.web.core.config import DB_PATH
from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import retry_on_locked


def _conn() -> sqlite3.Connection:
    conn = create_connection(DB_PATH, row_factory=sqlite3.Row)
    _ensure_tables(conn)
    return conn


def _write_with_retry(fn):
    # @@@locked-write-retry - scheduled task writes open short-lived SQLite
    # connections, so retry the whole write transaction on transient locks.
    return retry_on_locked(fn)


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            name TEXT NOT NULL,
            instruction TEXT NOT NULL,
            cron_expression TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            last_triggered_at INTEGER DEFAULT 0,
            next_trigger_at INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_task_runs (
            id TEXT PRIMARY KEY,
            scheduled_task_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            status TEXT NOT NULL,
            triggered_at INTEGER NOT NULL,
            started_at INTEGER DEFAULT 0,
            completed_at INTEGER DEFAULT 0,
            dispatch_result TEXT DEFAULT '',
            thread_run_id TEXT DEFAULT '',
            error TEXT DEFAULT ''
        )
    """)


def _validate_required(value: str, field_name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


def _validate_cron_expression(cron_expression: str) -> str:
    _validate_required(cron_expression, "cron_expression")
    if not croniter.is_valid(cron_expression):
        raise ValueError(f"Invalid cron expression: {cron_expression!r}")
    return cron_expression


def _compute_next_trigger_at(cron_expression: str, base_ms: int) -> int:
    base = datetime.fromtimestamp(base_ms / 1000)
    return int(croniter(cron_expression, base).get_next(datetime).timestamp() * 1000)


def _deserialize_task(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def _deserialize_run(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    raw = item.get("dispatch_result") or ""
    if raw:
        try:
            item["dispatch_result"] = json.loads(raw)
        except json.JSONDecodeError:
            item["dispatch_result"] = None
    else:
        item["dispatch_result"] = None
    return item


def list_scheduled_tasks() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM scheduled_tasks ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]


def get_scheduled_task(task_id: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)).fetchone()
        return _deserialize_task(row)


def create_scheduled_task(*, thread_id: str, name: str, instruction: str, cron_expression: str, **fields: Any) -> dict[str, Any]:
    thread_id = _validate_required(thread_id, "thread_id")
    name = _validate_required(name, "name")
    instruction = _validate_required(instruction, "instruction")
    cron_expression = _validate_cron_expression(cron_expression)

    now = int(time.time() * 1000)
    next_trigger_at = int(fields.get("next_trigger_at", 0)) or _compute_next_trigger_at(cron_expression, now)
    task_id = uuid.uuid4().hex
    def _do() -> dict[str, Any]:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO scheduled_tasks"
                " (id, thread_id, name, instruction, cron_expression, enabled, last_triggered_at, next_trigger_at, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    thread_id,
                    name,
                    instruction,
                    cron_expression,
                    int(fields.get("enabled", 1)),
                    int(fields.get("last_triggered_at", 0)),
                    next_trigger_at,
                    now,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row)

    return _write_with_retry(_do)


def update_scheduled_task(task_id: str, **fields: Any) -> dict[str, Any] | None:
    allowed = {
        "thread_id", "name", "instruction", "cron_expression", "enabled",
        "last_triggered_at", "next_trigger_at",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "thread_id" in updates:
        updates["thread_id"] = _validate_required(str(updates["thread_id"]), "thread_id")
    if "name" in updates:
        updates["name"] = _validate_required(str(updates["name"]), "name")
    if "instruction" in updates:
        updates["instruction"] = _validate_required(str(updates["instruction"]), "instruction")
    if "cron_expression" in updates:
        _validate_cron_expression(str(updates["cron_expression"]))
    if "cron_expression" in updates or ("last_triggered_at" in updates and "next_trigger_at" not in updates):
        current = get_scheduled_task(task_id)
        if current is not None:
            cron_expression = str(updates.get("cron_expression") or current["cron_expression"])
            base_ms = int(updates.get("last_triggered_at") or current.get("last_triggered_at") or 0) or int(time.time() * 1000)
            updates["next_trigger_at"] = _compute_next_trigger_at(cron_expression, base_ms)
    if not updates:
        return get_scheduled_task(task_id)
    updates["updated_at"] = int(time.time() * 1000)
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    def _do() -> dict[str, Any] | None:
        with _conn() as conn:
            conn.execute(f"UPDATE scheduled_tasks SET {set_clause} WHERE id = ?", (*updates.values(), task_id))
            conn.commit()
            row = conn.execute("SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)).fetchone()
            return _deserialize_task(row)

    return _write_with_retry(_do)


def delete_scheduled_task(task_id: str) -> bool:
    def _do() -> bool:
        with _conn() as conn:
            conn.execute("DELETE FROM scheduled_task_runs WHERE scheduled_task_id = ?", (task_id,))
            cur = conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cur.rowcount > 0

    return _write_with_retry(_do)


def create_scheduled_task_run(*, scheduled_task_id: str, thread_id: str, status: str, **fields: Any) -> dict[str, Any]:
    now = int(time.time() * 1000)
    run_id = uuid.uuid4().hex
    def _do() -> dict[str, Any] | None:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO scheduled_task_runs"
                " (id, scheduled_task_id, thread_id, status, triggered_at, started_at, completed_at, dispatch_result, thread_run_id, error)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    scheduled_task_id,
                    thread_id,
                    status,
                    int(fields.get("triggered_at", now)),
                    int(fields.get("started_at", 0)),
                    int(fields.get("completed_at", 0)),
                    json.dumps(fields["dispatch_result"]) if fields.get("dispatch_result") is not None else "",
                    fields.get("thread_run_id", ""),
                    fields.get("error", ""),
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM scheduled_task_runs WHERE id = ?", (run_id,)).fetchone()
            return _deserialize_run(row)

    return _write_with_retry(_do)


def update_scheduled_task_run(run_id: str, **fields: Any) -> dict[str, Any] | None:
    allowed = {
        "status", "triggered_at", "started_at", "completed_at",
        "dispatch_result", "thread_run_id", "error",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "dispatch_result" in updates:
        updates["dispatch_result"] = json.dumps(updates["dispatch_result"])
    if not updates:
        return get_scheduled_task_run(run_id)
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    def _do() -> dict[str, Any] | None:
        with _conn() as conn:
            conn.execute(f"UPDATE scheduled_task_runs SET {set_clause} WHERE id = ?", (*updates.values(), run_id))
            conn.commit()
            row = conn.execute("SELECT * FROM scheduled_task_runs WHERE id = ?", (run_id,)).fetchone()
            return _deserialize_run(row)

    return _write_with_retry(_do)


def get_scheduled_task_run(run_id: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM scheduled_task_runs WHERE id = ?", (run_id,)).fetchone()
        return _deserialize_run(row)


def list_scheduled_task_runs(scheduled_task_id: str) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_task_runs WHERE scheduled_task_id = ? ORDER BY triggered_at DESC",
            (scheduled_task_id,),
        ).fetchall()
        return [_deserialize_run(row) for row in rows]
