"""SQLite repository for eval trajectory persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from eval.models import RunTrajectory
from storage.providers.sqlite.connection import create_connection

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS eval_runs (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    user_message TEXT,
    final_response TEXT,
    status TEXT DEFAULT 'completed',
    run_tree_json TEXT,
    trajectory_json TEXT
);

CREATE TABLE IF NOT EXISTS eval_llm_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    parent_run_id TEXT,
    duration_ms REAL DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    model_name TEXT DEFAULT '',
    FOREIGN KEY (run_id) REFERENCES eval_runs(id)
);

CREATE TABLE IF NOT EXISTS eval_tool_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    parent_run_id TEXT,
    tool_name TEXT NOT NULL,
    tool_call_id TEXT DEFAULT '',
    duration_ms REAL DEFAULT 0,
    success INTEGER DEFAULT 1,
    error TEXT,
    args_summary TEXT DEFAULT '',
    result_summary TEXT DEFAULT '',
    FOREIGN KEY (run_id) REFERENCES eval_runs(id)
);

CREATE TABLE IF NOT EXISTS eval_metrics (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    timestamp TEXT,
    metrics_json TEXT,
    FOREIGN KEY (run_id) REFERENCES eval_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_eval_runs_thread ON eval_runs(thread_id, started_at);
CREATE INDEX IF NOT EXISTS idx_eval_tool_name ON eval_tool_calls(tool_name);
CREATE INDEX IF NOT EXISTS idx_eval_metrics_run ON eval_metrics(run_id, tier);
"""


class SQLiteEvalRepo:
    """Repository boundary for eval DB SQL operations."""

    def __init__(self, db_path: str | Path, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        if conn is not None:
            self._conn = conn
        else:
            self._conn = create_connection(db_path, row_factory=sqlite3.Row)

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def ensure_schema(self) -> None:
        self._conn.executescript(_SCHEMA_SQL)

    def upsert_run_header(
        self,
        *,
        run_id: str,
        thread_id: str,
        started_at: str,
        user_message: str,
        status: str,
    ) -> None:
        self._conn.execute(
            "INSERT INTO eval_runs (id, thread_id, started_at, user_message, status) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "thread_id = excluded.thread_id, "
            "started_at = excluded.started_at, "
            "user_message = excluded.user_message, "
            "status = excluded.status",
            (run_id, thread_id, started_at, user_message, status),
        )
        self._conn.commit()

    def finalize_run(
        self,
        *,
        run_id: str,
        finished_at: str,
        final_response: str,
        status: str,
        run_tree_json: str,
        trajectory_json: str,
    ) -> None:
        result = self._conn.execute(
            "UPDATE eval_runs SET finished_at = ?, final_response = ?, status = ?, run_tree_json = ?, trajectory_json = ? WHERE id = ?",
            (finished_at, final_response, status, run_tree_json, trajectory_json, run_id),
        )
        if result.rowcount != 1:
            raise RuntimeError(f"SQLite eval repo expected existing run for finalize_run: {run_id}")
        self._conn.commit()

    def save_trajectory(self, trajectory: RunTrajectory, trajectory_json: str) -> str:
        run_id = trajectory.id
        self._conn.execute(
            "INSERT INTO eval_runs (id, thread_id, started_at, finished_at, "
            "user_message, final_response, status, run_tree_json, trajectory_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                trajectory.thread_id,
                trajectory.started_at,
                trajectory.finished_at,
                trajectory.user_message,
                trajectory.final_response,
                trajectory.status,
                trajectory.run_tree_json,
                trajectory_json,
            ),
        )

        for call in trajectory.llm_calls:
            self._conn.execute(
                "INSERT INTO eval_llm_calls (id, run_id, parent_run_id, "
                "duration_ms, input_tokens, output_tokens, total_tokens, "
                "cost_usd, model_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid4()),
                    run_id,
                    call.parent_run_id,
                    call.duration_ms,
                    call.input_tokens,
                    call.output_tokens,
                    call.total_tokens,
                    call.cost_usd,
                    call.model_name,
                ),
            )

        for call in trajectory.tool_calls:
            self._conn.execute(
                "INSERT INTO eval_tool_calls (id, run_id, parent_run_id, "
                "tool_name, tool_call_id, duration_ms, success, error, "
                "args_summary, result_summary) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid4()),
                    run_id,
                    call.parent_run_id,
                    call.tool_name,
                    call.tool_call_id,
                    call.duration_ms,
                    int(call.success),
                    call.error,
                    call.args_summary,
                    call.result_summary,
                ),
            )
        self._conn.commit()
        return run_id

    def save_metrics(self, run_id: str, tier: str, timestamp: str, metrics_json: str) -> None:
        self._conn.execute(
            "INSERT INTO eval_metrics (id, run_id, tier, timestamp, metrics_json) VALUES (?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                run_id,
                tier,
                timestamp,
                metrics_json,
            ),
        )
        self._conn.commit()

    def get_trajectory_json(self, run_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT trajectory_json FROM eval_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if not row:
            return None
        return row["trajectory_json"]

    def list_runs(self, thread_id: str | None = None, limit: int = 50) -> list[dict]:
        if thread_id:
            rows = self._conn.execute(
                "SELECT id, thread_id, started_at, finished_at, status, "
                "user_message FROM eval_runs "
                "WHERE thread_id = ? ORDER BY started_at DESC LIMIT ?",
                (thread_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, thread_id, started_at, finished_at, status, user_message FROM eval_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_metrics(self, run_id: str, tier: str | None = None) -> list[dict]:
        if tier:
            rows = self._conn.execute(
                "SELECT id, tier, timestamp, metrics_json FROM eval_metrics WHERE run_id = ? AND tier = ?",
                (run_id, tier),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, tier, timestamp, metrics_json FROM eval_metrics WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]
