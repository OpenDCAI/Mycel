"""
Sandbox Monitor API - View-Ready Endpoints

All endpoints return view-ready data that frontend can directly render.
No business logic in frontend.
"""

import asyncio
import json
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.web.core.config import DB_PATH
from backend.web.services.monitor_service import build_evaluation_operator_surface
from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite, resolve_role_db_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_DB_PATH = resolve_role_db_path(SQLiteDBRole.SANDBOX)
RUN_EVENT_DB_PATH = resolve_role_db_path(SQLiteDBRole.RUN_EVENT)

router = APIRouter(prefix="/api/monitor")


def get_db():
    # @@@fastapi-threadpool-sqlite - sync endpoints may execute in worker
    # threads; disable same-thread guard for shared request-scoped connection.
    db = connect_sqlite(SANDBOX_DB_PATH, row_factory=sqlite3.Row, check_same_thread=False)
    try:
        yield db
    finally:
        db.close()


class EvaluationCreateRequest(BaseModel):
    dataset: str = "SWE-bench/SWE-bench_Lite"
    split: str = "test"
    start: int = 0
    count: int = Field(default=5, ge=1, le=50)
    prompt_profile: str = "heuristic"
    model_name: str | None = None
    timeout_sec: int = Field(default=180, ge=30, le=3600)
    eval_timeout_sec: int = Field(default=10800, ge=300, le=86400)
    git_timeout_sec: int = Field(default=90, ge=15, le=600)
    recursion_limit: int = Field(default=256, ge=1, le=512)
    sandbox: str = "local"
    cwd: str = str(PROJECT_ROOT)
    arm: str = "monitor"
    output_dir: str = "artifacts/swebench"
    run_eval: bool = True
    thread_prefix: str = "swebench"


def _ensure_evaluation_tables() -> None:
    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_jobs (
                evaluation_id TEXT PRIMARY KEY,
                dataset TEXT NOT NULL,
                split TEXT NOT NULL,
                start_idx INTEGER NOT NULL,
                slice_count INTEGER NOT NULL,
                prompt_profile TEXT NOT NULL,
                timeout_sec INTEGER NOT NULL,
                recursion_limit INTEGER NOT NULL,
                sandbox TEXT NOT NULL,
                cwd TEXT,
                arm TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_job_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evaluation_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                run_id TEXT,
                start_idx INTEGER NOT NULL,
                item_index INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(evaluation_id, thread_id),
                FOREIGN KEY (evaluation_id) REFERENCES evaluation_jobs(evaluation_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_evaluation_job_threads_eval
            ON evaluation_job_threads(evaluation_id, item_index)
            """
        )
        conn.commit()


def _ensure_eval_task_map(app: object) -> dict[str, asyncio.Task]:
    tasks = getattr(app.state, "evaluation_tasks", None)
    if tasks is None:
        tasks = {}
        app.state.evaluation_tasks = tasks
    return tasks


def _resolve_output_dir(cwd: str, output_dir: str) -> Path:
    root = Path(output_dir).expanduser()
    if not root.is_absolute():
        root = (Path(cwd).expanduser().resolve() / root).resolve()
    return root


def _build_run_slice_command(payload: EvaluationCreateRequest, evaluation_id: str) -> list[str]:
    cmd = [
        "uv",
        "run",
        "python",
        "eval/swebench/run_slice.py",
        "--dataset",
        payload.dataset,
        "--split",
        payload.split,
        "--start",
        str(payload.start),
        "--count",
        str(payload.count),
        "--run-id",
        evaluation_id,
        "--arm",
        payload.arm,
        "--prompt-profile",
        payload.prompt_profile,
        "--timeout-sec",
        str(payload.timeout_sec),
        "--eval-timeout-sec",
        str(payload.eval_timeout_sec),
        "--git-timeout-sec",
        str(payload.git_timeout_sec),
        "--recursion-limit",
        str(payload.recursion_limit),
        "--output-dir",
        payload.output_dir,
        "--thread-prefix",
        payload.thread_prefix,
    ]
    if not payload.run_eval:
        cmd.append("--no-eval")
    if payload.model_name:
        cmd.extend(["--model-name", payload.model_name])
    return cmd


def _update_evaluation_job_status(evaluation_id: str, status: str, notes: str) -> None:
    now = datetime.now().isoformat()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            "UPDATE evaluation_jobs SET status = ?, notes = ?, updated_at = ? WHERE evaluation_id = ?",
            (status, notes, now, evaluation_id),
        )
        conn.commit()


def _ingest_evaluation_threads(
    *,
    evaluation_id: str,
    thread_prefix: str,
    start_idx: int,
    run_dir: Path,
) -> int:
    ids_path = run_dir / "instance_ids.txt"
    if not ids_path.exists():
        return 0
    instance_ids = [line.strip() for line in ids_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    now = datetime.now().isoformat()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("DELETE FROM evaluation_job_threads WHERE evaluation_id = ?", (evaluation_id,))
        for idx, instance_id in enumerate(instance_ids):
            thread_id = f"{thread_prefix}-{evaluation_id}-{instance_id}"
            run = _load_run_stats(thread_id, None)
            conn.execute(
                """
                INSERT INTO evaluation_job_threads (
                    evaluation_id, thread_id, run_id, start_idx, item_index, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation_id,
                    thread_id,
                    run.get("run_id"),
                    start_idx + idx,
                    idx,
                    now,
                ),
            )
        conn.commit()
    return len(instance_ids)


async def _run_evaluation_job(evaluation_id: str, payload: EvaluationCreateRequest) -> None:
    cwd = str(Path(payload.cwd).expanduser().resolve())
    output_root = _resolve_output_dir(cwd, payload.output_dir)
    run_dir = output_root / evaluation_id
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir / "monitor_stdout.log"
    stderr_path = run_dir / "monitor_stderr.log"
    command = _build_run_slice_command(payload, evaluation_id)
    # @@@monitor-eval-sandbox-env - pass sandbox selection via env so
    # run_slice -> LeonAgent resolves non-local provider, and isolate sandbox
    # state per evaluation run.
    env = dict(os.environ)
    env["LEON_SANDBOX"] = payload.sandbox
    env["LEON_SANDBOX_DB_PATH"] = str(run_dir / "sandbox.db")
    try:
        # @@@monitor-eval-direct-runner - evaluate by invoking SWE runner directly, not by sending a control prompt to another agent.
        with stdout_path.open("wb") as stdout_fh, stderr_path.open("wb") as stderr_fh:
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                stdout=stdout_fh,
                stderr=stderr_fh,
                env=env,
                start_new_session=True,
            )
        _update_evaluation_job_status(
            evaluation_id,
            "running",
            (f"runner=direct pid={proc.pid} sandbox={payload.sandbox} run_dir={run_dir} stdout_log={stdout_path} stderr_log={stderr_path}"),
        )
        # @@@monitor-eval-hard-timeout-budget - wall-time must include both solve budget and harness scoring budget for batch runs.
        solve_budget_sec = payload.timeout_sec * payload.count
        eval_budget_sec = payload.eval_timeout_sec if payload.run_eval else 0
        hard_timeout_sec = solve_budget_sec + eval_budget_sec + 180
        try:
            await asyncio.wait_for(proc.wait(), timeout=hard_timeout_sec)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            notes = (
                f"runner=direct timeout={hard_timeout_sec}s solve_budget={solve_budget_sec}s "
                f"eval_budget={eval_budget_sec}s sandbox={payload.sandbox} run_dir={run_dir} "
                f"stdout_log={stdout_path} stderr_log={stderr_path}"
            )
            _update_evaluation_job_status(evaluation_id, "error", notes)
            return
        if proc.returncode != 0:
            notes = (
                f"runner=direct rc={proc.returncode} sandbox={payload.sandbox} run_dir={run_dir} "
                f"stdout_log={stdout_path} stderr_log={stderr_path}"
            )
            _update_evaluation_job_status(evaluation_id, "error", notes)
            return
        thread_count = _ingest_evaluation_threads(
            evaluation_id=evaluation_id,
            thread_prefix=payload.thread_prefix,
            start_idx=payload.start,
            run_dir=run_dir,
        )
        notes = (
            f"runner=direct rc=0 sandbox={payload.sandbox} run_dir={run_dir} stdout_log={stdout_path} "
            f"stderr_log={stderr_path} threads={thread_count}"
        )
        score = _load_evaluation_score(
            evaluation_id=evaluation_id,
            cwd=payload.cwd,
            notes=notes,
        )
        final_status = _derive_evaluation_status("completed", score)
        _update_evaluation_job_status(evaluation_id, final_status, notes)
    except Exception as exc:
        notes = f"runner=direct error={exc} sandbox={payload.sandbox} run_dir={run_dir} stdout_log={stdout_path} stderr_log={stderr_path}"
        _update_evaluation_job_status(evaluation_id, "error", notes)


def _load_latest_session(db: sqlite3.Connection, thread_id: str) -> sqlite3.Row | None:
    return db.execute(
        """
        SELECT chat_session_id, status, started_at, last_active_at
        FROM chat_sessions
        WHERE thread_id = ?
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (thread_id,),
    ).fetchone()


def _load_run_stats(thread_id: str, run_id: str | None) -> dict:
    if not RUN_EVENT_DB_PATH.exists():
        return {"run_id": run_id, "event_count": 0, "last_seq": 0, "last_event_at": None, "last_event_ago": None}
    with sqlite3.connect(str(RUN_EVENT_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        if run_id:
            row = conn.execute(
                """
                SELECT run_id, COUNT(*) AS event_count, MAX(seq) AS last_seq, MAX(created_at) AS last_event_at
                FROM run_events
                WHERE thread_id = ? AND run_id = ?
                GROUP BY run_id
                """,
                (thread_id, run_id),
            ).fetchone()
            if row:
                return {
                    "run_id": row["run_id"],
                    "event_count": int(row["event_count"] or 0),
                    "last_seq": int(row["last_seq"] or 0),
                    "last_event_at": row["last_event_at"],
                    "last_event_ago": format_time_ago(row["last_event_at"]) if row["last_event_at"] else None,
                }
        row = conn.execute(
            """
            SELECT run_id, COUNT(*) AS event_count, MAX(seq) AS last_seq, MAX(created_at) AS last_event_at
            FROM run_events
            WHERE thread_id = ?
            GROUP BY run_id
            ORDER BY last_seq DESC
            LIMIT 1
            """,
            (thread_id,),
        ).fetchone()
        if not row:
            return {"run_id": run_id, "event_count": 0, "last_seq": 0, "last_event_at": None, "last_event_ago": None}
        return {
            "run_id": row["run_id"],
            "event_count": int(row["event_count"] or 0),
            "last_seq": int(row["last_seq"] or 0),
            "last_event_at": row["last_event_at"],
            "last_event_ago": format_time_ago(row["last_event_at"]) if row["last_event_at"] else None,
        }


def _read_json_file(path: Path | None) -> dict | None:
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_jsonl_rows(path: Path | None) -> list[dict]:
    if not path or not path.exists():
        return []
    rows: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                text = line.strip()
                if not text:
                    continue
                obj = json.loads(text)
                if isinstance(obj, dict):
                    rows.append(obj)
    except Exception:
        return []
    return rows


def _note_value(notes: str, key: str) -> str | None:
    prefix = f"{key}="
    for token in (notes or "").split():
        if token.startswith(prefix):
            return token[len(prefix) :]
    return None


def _resolve_eval_run_dir(evaluation_id: str, cwd: str | None, notes: str) -> Path | None:
    candidates: list[Path] = []
    note_run_dir = _note_value(notes, "run_dir")
    if note_run_dir:
        candidates.append(Path(note_run_dir).expanduser())
    if cwd:
        candidates.append((Path(cwd).expanduser().resolve() / "artifacts" / "swebench" / evaluation_id).resolve())

    for run_dir in candidates:
        if (run_dir / "run_manifest.json").exists():
            return run_dir
    for run_dir in candidates:
        if run_dir.exists():
            return run_dir
    return None


def _infer_sandbox_from_run_id(run_id: str, fallback: str | None = None) -> str:
    value = run_id.lower()
    if "docker" in value:
        return "docker"
    if "daytona" in value:
        return "daytona"
    if "local" in value:
        return "local"
    return fallback or "local"


def _iter_artifact_run_dirs(cwd_candidates: list[str], max_dirs: int = 500) -> list[Path]:
    run_dirs: list[Path] = []
    seen: set[str] = set()
    for cwd in cwd_candidates:
        if not cwd:
            continue
        root = (Path(cwd).expanduser().resolve() / "artifacts" / "swebench").resolve()
        if not root.exists():
            continue
        for item in sorted(root.glob("eval-*"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
            manifest_path = item / "run_manifest.json"
            if not item.is_dir() or not manifest_path.exists():
                continue
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            run_dirs.append(item)
            if len(run_dirs) >= max_dirs:
                return run_dirs
    return run_dirs


def _backfill_evaluations_from_artifacts(app: object | None, base_cwd: str = str(PROJECT_ROOT)) -> int:
    # @@@eval-artifact-backfill-throttle - list endpoint polls every 2.5s; throttle filesystem backfill scan to keep monitor responsive.
    now = time.time()
    if app is not None:
        last_ts = float(getattr(app.state, "eval_artifact_backfill_ts", 0.0) or 0.0)
        if now - last_ts < 20.0:
            return 0

    _ensure_evaluation_tables()
    inserted = 0
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        existing_ids = {str(row["evaluation_id"]) for row in conn.execute("SELECT evaluation_id FROM evaluation_jobs").fetchall()}
        cwd_rows = conn.execute("SELECT DISTINCT cwd FROM evaluation_jobs WHERE cwd IS NOT NULL AND cwd != ''").fetchall()
        cwd_candidates = [base_cwd] + [str(row["cwd"]) for row in cwd_rows if row["cwd"]]
        run_dirs = _iter_artifact_run_dirs(cwd_candidates)
        for run_dir in run_dirs:
            manifest = _read_json_file(run_dir / "run_manifest.json") or {}
            evaluation_id = str(manifest.get("run_id") or run_dir.name)
            if not evaluation_id.startswith("eval-"):
                continue
            if evaluation_id in existing_ids:
                continue

            created_at = str(manifest.get("generated_at_utc") or datetime.now().isoformat())
            dataset = str(manifest.get("dataset") or "SWE-bench/SWE-bench_Lite")
            split = str(manifest.get("split") or "test")
            start_idx = int(manifest.get("start") or 0)
            slice_count = int(manifest.get("count") or 0)
            prompt_profile = str(manifest.get("prompt_profile") or "heuristic")
            timeout_sec = int(manifest.get("timeout_sec") or 180)
            recursion_limit = int(manifest.get("recursion_limit") or 256)
            sandbox = _infer_sandbox_from_run_id(evaluation_id, fallback=manifest.get("sandbox"))
            cwd = str(run_dir.parents[2]) if len(run_dir.parents) >= 3 else base_cwd
            arm = str(manifest.get("arm") or "artifact_backfill")
            status = "error" if str(manifest.get("eval_error") or "").strip() else "completed"
            notes = f"runner=artifact_backfill run_dir={run_dir}"
            conn.execute(
                """
                INSERT INTO evaluation_jobs (
                    evaluation_id, dataset, split, start_idx, slice_count, prompt_profile,
                    timeout_sec, recursion_limit, sandbox, cwd, arm, status, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation_id,
                    dataset,
                    split,
                    start_idx,
                    slice_count,
                    prompt_profile,
                    timeout_sec,
                    recursion_limit,
                    sandbox,
                    cwd,
                    arm,
                    status,
                    notes,
                    created_at,
                    created_at,
                ),
            )

            trace_path = Path(str(manifest.get("trace_summaries_path") or (run_dir / "trace_summaries.jsonl"))).expanduser()
            trace_rows = _read_jsonl_rows(trace_path)
            if trace_rows:
                for idx, row in enumerate(trace_rows):
                    instance_id = str(row.get("instance_id") or f"item-{idx}")
                    thread_id = str(row.get("thread_id") or f"swebench-{evaluation_id}-{instance_id}")
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO evaluation_job_threads (
                            evaluation_id, thread_id, run_id, start_idx, item_index, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            evaluation_id,
                            thread_id,
                            evaluation_id,
                            start_idx + idx,
                            idx,
                            created_at,
                        ),
                    )
            inserted += 1
            existing_ids.add(evaluation_id)
        conn.commit()

    if app is not None:
        app.state.eval_artifact_backfill_ts = now
        app.state.eval_artifact_backfill_inserted = int(getattr(app.state, "eval_artifact_backfill_inserted", 0) or 0) + inserted
    return inserted


def _pct(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100.0, 2)


def _derive_evaluation_status(status: str, score: dict | None) -> str:
    if status == "running":
        return status
    if not score:
        return status
    if str(score.get("manifest_eval_error") or "").strip():
        return "provisional"
    if not bool(score.get("scored")):
        return "provisional"
    return "completed_with_errors" if int(score.get("error_instances") or 0) > 0 else "completed"


def _count_live_eval_threads(evaluation_id: str) -> int:
    if not DB_PATH.exists():
        return 0
    thread_prefix = f"swebench-{evaluation_id}-%"
    with sqlite3.connect(str(DB_PATH)) as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT thread_id) FROM checkpoints WHERE thread_id LIKE ?",
            (thread_prefix,),
        ).fetchone()
    return int(row[0] or 0) if row else 0


def _load_live_eval_session_progress(evaluation_id: str, cwd: str | None, notes: str) -> dict | None:
    run_dir = _resolve_eval_run_dir(evaluation_id, cwd, notes)
    if not run_dir:
        return None
    trace_db = run_dir / "sandbox.db"
    if not trace_db.exists():
        return None
    thread_prefix = f"swebench-{evaluation_id}-%"
    try:
        with sqlite3.connect(str(trace_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS running,
                    SUM(CASE WHEN status != 'active' THEN 1 ELSE 0 END) AS done,
                    MAX(idle_ttl_sec) AS idle_ttl_sec,
                    ROUND((julianday('now') - julianday(MAX(last_active_at))) * 24 * 60, 1) AS idle_minutes
                FROM chat_sessions
                WHERE thread_id LIKE ?
                """,
                (thread_prefix,),
            ).fetchone()
    except sqlite3.OperationalError:
        # @@@eval-session-table-warmup - sandbox.db may exist before chat_sessions table initialization; treat as no live session data.
        return None
    if not row:
        return None
    total = int(row["total"] or 0)
    running = int(row["running"] or 0)
    done = int(row["done"] or 0)
    idle_ttl_sec = int(row["idle_ttl_sec"] or 300)
    idle_minutes = float(row["idle_minutes"]) if row["idle_minutes"] is not None else None
    if total <= 0:
        return None
    # @@@eval-progress-live-session - when thread mapping rows are not
    # persisted yet, use per-run sandbox session states for true running/done
    # counts.
    # @@@eval-running-freshness - treat stale "active" sessions as non-running
    # to avoid fake-running UI after runner exits unexpectedly.
    stale_after_minutes = max(2.0, (idle_ttl_sec / 60.0) + 1.0)
    active_recent = bool(running > 0 and idle_minutes is not None and idle_minutes <= stale_after_minutes)
    running_effective = running if active_recent else 0
    done_effective = done if active_recent else min(total, done + running)
    return {
        "total": total,
        "running": max(0, running_effective),
        "done": max(0, done_effective),
        "idle_minutes": idle_minutes,
        "idle_ttl_sec": idle_ttl_sec,
        "stale_after_minutes": stale_after_minutes,
        "active_recent": active_recent,
    }


def _load_live_eval_sessions(evaluation_id: str, cwd: str | None, notes: str) -> list[dict]:
    run_dir = _resolve_eval_run_dir(evaluation_id, cwd, notes)
    if not run_dir:
        return []
    trace_db = run_dir / "sandbox.db"
    if not trace_db.exists():
        return []
    thread_prefix = f"swebench-{evaluation_id}-%"
    try:
        with sqlite3.connect(str(trace_db)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT thread_id, chat_session_id, status, started_at, last_active_at, ended_at, close_reason
                FROM chat_sessions
                WHERE thread_id LIKE ?
                ORDER BY started_at ASC
                """,
                (thread_prefix,),
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    sessions: list[dict] = []
    for row in rows:
        sessions.append(
            {
                "thread_id": str(row["thread_id"]),
                "chat_session_id": str(row["chat_session_id"]),
                "status": str(row["status"] or "active"),
                "started_at": row["started_at"],
                "last_active_at": row["last_active_at"],
                "ended_at": row["ended_at"],
                "close_reason": row["close_reason"],
            }
        )
    return sessions


def _is_eval_runner_alive(evaluation_id: str, notes: str) -> bool:
    # @@@eval-runner-pid-liveness - after backend restart, task map is empty;
    # use persisted runner pid as direct liveness source before session rows
    # appear.
    m = re.search(r"\bpid=(\d+)\b", notes or "")
    if not m:
        return False
    pid = int(m.group(1))
    proc_dir = Path(f"/proc/{pid}")
    if not proc_dir.exists():
        return False
    try:
        cmdline = (proc_dir / "cmdline").read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    if "run_slice.py" not in cmdline:
        return False
    if evaluation_id and evaluation_id not in cmdline:
        return False
    return True


def _load_evaluation_score(evaluation_id: str, cwd: str | None, notes: str) -> dict:
    run_dir = _resolve_eval_run_dir(evaluation_id, cwd, notes)
    manifest_path = (run_dir / "run_manifest.json") if run_dir else None
    manifest = _read_json_file(manifest_path) or {}

    summary_path: Path | None = None
    if manifest.get("eval_summary_path"):
        summary_path = Path(str(manifest["eval_summary_path"])).expanduser()
    elif cwd:
        root = Path(cwd).expanduser().resolve()
        for candidate in (
            root / f"{root.name}.{evaluation_id}.json",
            root / f"leonai-main.{evaluation_id}.json",
        ):
            if candidate.exists():
                summary_path = candidate
                break

    summary = _read_json_file(summary_path) or {}
    trace_summaries_path: Path | None = None
    if manifest.get("trace_summaries_path"):
        trace_summaries_path = Path(str(manifest["trace_summaries_path"])).expanduser()
    trace_rows = _read_jsonl_rows(trace_summaries_path)

    manifest_total = int(manifest.get("instances_total") or 0)
    summary_total = int(summary.get("total_instances") or 0)
    submitted_instances = int(summary.get("submitted_instances") or 0)
    completed_instances = int(summary.get("completed_instances") or 0)
    resolved_instances = int(summary.get("resolved_instances") or 0)
    unresolved_instances = int(summary.get("unresolved_instances") or 0)
    empty_patch_instances = int(summary.get("empty_patch_instances") or manifest.get("empty_patch_total") or 0)
    error_instances = int(summary.get("error_instances") or manifest.get("errors_total") or 0)

    total_instances = manifest_total or summary_total
    if total_instances <= 0:
        total_instances = max(summary_total, submitted_instances, completed_instances, resolved_instances + unresolved_instances)
    if submitted_instances > total_instances:
        total_instances = submitted_instances
    if completed_instances > total_instances:
        total_instances = completed_instances

    patch_base = submitted_instances or total_instances
    non_empty_patch_instances = max(patch_base - empty_patch_instances, 0)

    active_trace_threads = 0
    tool_call_threads = 0
    tool_calls_total = 0
    for row in trace_rows:
        tool_calls = int(row.get("tool_calls_total") or 0)
        checkpoints = int(row.get("checkpoint_count") or 0)
        messages = int(row.get("message_count") or 0)
        if checkpoints > 0 or messages > 0:
            active_trace_threads += 1
        if tool_calls > 0:
            tool_call_threads += 1
        tool_calls_total += tool_calls
    avg_tool_calls_per_active_thread = round(tool_calls_total / active_trace_threads, 2) if active_trace_threads > 0 else None

    recursion_limit = int(manifest.get("recursion_limit") or 0)
    recursion_cap_hits = 0
    if recursion_limit > 0:
        recursion_cap_hits = sum(1 for row in trace_rows if int(row.get("last_step") or 0) >= recursion_limit)

    # @@@eval-score-source - score must come from persisted run artifacts instead of in-memory thread counters so reload stays consistent.
    score_gate = "final" if bool(summary_path and summary) and not str(manifest.get("eval_error") or "").strip() else "provisional"
    publishable = score_gate == "final"

    return {
        "scored": bool(summary_path and summary),
        "score_gate": score_gate,
        "publishable": publishable,
        "manifest_eval_error": str(manifest.get("eval_error") or "").strip(),
        "run_dir": str(run_dir) if run_dir else None,
        "manifest_path": str(manifest_path) if manifest_path else None,
        "eval_summary_path": str(summary_path) if summary_path else None,
        "trace_summaries_path": str(trace_summaries_path) if trace_summaries_path else None,
        "total_instances": total_instances,
        "submitted_instances": submitted_instances,
        "completed_instances": completed_instances,
        "resolved_instances": resolved_instances,
        "unresolved_instances": unresolved_instances,
        "non_empty_patch_instances": non_empty_patch_instances,
        "empty_patch_instances": empty_patch_instances,
        "error_instances": error_instances,
        "primary_score_pct": _pct(resolved_instances, total_instances),
        "completed_rate_pct": _pct(completed_instances, total_instances),
        "resolved_rate_pct": _pct(resolved_instances, total_instances),
        "non_empty_patch_rate_pct": _pct(non_empty_patch_instances, total_instances),
        "empty_patch_rate_pct": _pct(empty_patch_instances, total_instances),
        "active_trace_threads": active_trace_threads,
        "active_trace_thread_rate_pct": _pct(active_trace_threads, total_instances),
        "tool_call_threads": tool_call_threads,
        "tool_call_thread_rate_pct": _pct(tool_call_threads, total_instances),
        "tool_calls_total": tool_calls_total,
        "avg_tool_calls_per_active_thread": avg_tool_calls_per_active_thread,
        "recursion_limit": recursion_limit or None,
        "recursion_cap_hits": recursion_cap_hits,
        "recursion_cap_hit_rate_pct": _pct(recursion_cap_hits, active_trace_threads),
    }


def _backfill_eval_threads_from_score(
    conn: sqlite3.Connection,
    *,
    evaluation_id: str,
    start_idx: int,
    created_at: str | None,
    score: dict | None,
) -> int:
    if not score:
        return 0
    trace_path_value = score.get("trace_summaries_path")
    if not trace_path_value:
        return 0
    trace_path = Path(str(trace_path_value)).expanduser()
    trace_rows = _read_jsonl_rows(trace_path)
    if not trace_rows:
        return 0

    ts = created_at or datetime.now().isoformat()
    inserted = 0
    for idx, row in enumerate(trace_rows):
        instance_id = str(row.get("instance_id") or f"item-{idx}")
        thread_id = str(row.get("thread_id") or f"swebench-{evaluation_id}-{instance_id}")
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO evaluation_job_threads (
                evaluation_id, thread_id, run_id, start_idx, item_index, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation_id,
                thread_id,
                evaluation_id,
                start_idx + idx,
                idx,
                ts,
            ),
        )
        if int(cur.rowcount or 0) > 0:
            inserted += 1
    return inserted


def format_time_ago(iso_timestamp: str) -> str:
    """Convert ISO timestamp to human readable 'X hours ago'"""
    if not iso_timestamp:
        return "never"
    # @@@ naive-local — SQLite timestamps are local time, compare with local now
    if "Z" in iso_timestamp:
        iso_timestamp = iso_timestamp.replace("Z", "")
    if "+" in iso_timestamp:
        iso_timestamp = iso_timestamp.split("+")[0]
    dt = datetime.fromisoformat(iso_timestamp)
    now = datetime.now()
    delta = now - dt

    if delta.days > 0:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    minutes = (delta.seconds % 3600) // 60
    if minutes > 0:
        return f"{minutes}m ago"
    return "just now"


def make_badge(desired, observed):
    """Build a state badge dict handling null states"""
    if not desired and not observed:
        return {"desired": None, "observed": None, "converged": True, "color": "green", "text": "destroyed"}
    if desired == observed:
        return {"desired": desired, "observed": observed, "converged": True, "color": "green", "text": observed}
    return {
        "desired": desired,
        "observed": observed,
        "converged": False,
        "color": "yellow",
        "text": f"{observed} → {desired}",
    }


def load_thread_mode_map(thread_ids: list[str]) -> dict[str, dict]:
    """Load thread mode metadata from thread_config."""
    if not thread_ids or not DB_PATH.exists():
        return {}
    try:
        with connect_sqlite(DB_PATH, row_factory=sqlite3.Row) as conn:
            placeholders = ",".join("?" for _ in thread_ids)
            rows = conn.execute(
                f"""
                SELECT thread_id, thread_mode, keep_full_trace
                FROM thread_config
                WHERE thread_id IN ({placeholders})
                """,
                thread_ids,
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    mode_map = {}
    for row in rows:
        mode_map[row["thread_id"]] = {
            "thread_mode": row["thread_mode"] or "normal",
            "keep_full_trace": str(row["keep_full_trace"] or "0") in {"1", "true", "True"},
        }
    return mode_map


def load_thread_mode(thread_id: str) -> dict:
    """Load single thread mode metadata."""
    mode_map = load_thread_mode_map([thread_id])
    return mode_map.get(thread_id, {"thread_mode": "normal", "keep_full_trace": False})


def _list_checkpoint_threads_for_evaluation(evaluation_id: str) -> list[str]:
    """List checkpoint-only evaluation thread IDs before thread/session rows are persisted."""
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(str(DB_PATH)) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT thread_id
            FROM checkpoints
            WHERE thread_id LIKE ?
            ORDER BY rowid DESC
            """,
            (f"swebench-{evaluation_id}-%",),
        ).fetchall()
    return [str(row[0]) for row in rows if row and row[0]]


def _list_running_eval_checkpoint_threads() -> list[dict[str, str | None]]:
    """Expose running SWE-bench threads that only exist in checkpoints, not chat_sessions yet."""
    if not DB_PATH.exists():
        return []

    items: list[dict[str, str | None]] = []
    seen: set[str] = set()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            jobs = conn.execute(
                """
                SELECT evaluation_id, status, created_at, updated_at
                FROM evaluation_jobs
                WHERE status = 'running'
                ORDER BY created_at DESC
                """
            ).fetchall()
        except sqlite3.OperationalError as exc:
            # @@@compat-monitor-missing-eval-table - transplanted monitor must
            # still render on databases that have never created evaluation
            # tables.
            if "no such table: evaluation_jobs" in str(exc):
                return []
            raise
        for job in jobs:
            for thread_id in _list_checkpoint_threads_for_evaluation(str(job["evaluation_id"])):
                if thread_id in seen:
                    continue
                seen.add(thread_id)
                items.append(
                    {
                        "thread_id": thread_id,
                        "last_active": str(job["updated_at"] or job["created_at"] or ""),
                        "evaluation_id": str(job["evaluation_id"]),
                    }
                )
    return items


def load_run_candidates(thread_id: str, limit: int = 20) -> list[dict]:
    """List recent run_ids for a thread with basic stats."""
    if not RUN_EVENT_DB_PATH.exists():
        return []
    # @@@run-candidates - Keep selector data lightweight so session page can switch run trace quickly.
    with sqlite3.connect(str(RUN_EVENT_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                run_id,
                COUNT(*) AS event_count,
                MIN(seq) AS first_seq,
                MAX(seq) AS last_seq,
                MIN(created_at) AS started_at,
                MAX(created_at) AS ended_at
            FROM run_events
            WHERE thread_id = ?
            GROUP BY run_id
            ORDER BY MAX(seq) DESC
            LIMIT ?
            """,
            (thread_id, limit),
        ).fetchall()
        return [
            {
                "run_id": row["run_id"],
                "event_count": int(row["event_count"] or 0),
                "first_seq": int(row["first_seq"] or 0),
                "last_seq": int(row["last_seq"] or 0),
                "started_at": row["started_at"],
                "started_ago": format_time_ago(row["started_at"]) if row["started_at"] else None,
                "ended_at": row["ended_at"],
                "ended_ago": format_time_ago(row["ended_at"]) if row["ended_at"] else None,
            }
            for row in rows
        ]


def list_trace_runs(offset: int = 0, limit: int = 50) -> dict[str, Any]:
    """List recent trace-backed runs across all threads."""
    if not RUN_EVENT_DB_PATH.exists():
        return {
            "title": "Recent Traces",
            "count": 0,
            "items": [],
            "pagination": {
                "offset": offset,
                "limit": limit,
                "total": 0,
                "page": 1,
                "has_prev": False,
                "has_next": False,
                "prev_offset": None,
                "next_offset": None,
            },
        }

    with sqlite3.connect(str(RUN_EVENT_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        total_row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM (
                SELECT 1
                FROM run_events
                WHERE run_id NOT LIKE 'activity_%'
                GROUP BY thread_id, run_id
            )
            """
        ).fetchone()
        total = int(total_row["total"] if total_row else 0)
        rows = conn.execute(
            """
            SELECT
                thread_id,
                run_id,
                COUNT(*) AS event_count,
                SUM(CASE WHEN event_type = 'tool_call' THEN 1 ELSE 0 END) AS tool_call_count,
                SUM(CASE WHEN event_type = 'tool_result' THEN 1 ELSE 0 END) AS tool_result_count,
                MIN(created_at) AS started_at,
                MAX(created_at) AS last_event_at,
                MAX(CASE WHEN event_type = 'run_done' THEN 1 ELSE 0 END) AS has_run_done
            FROM run_events
            WHERE run_id NOT LIKE 'activity_%'
            GROUP BY thread_id, run_id
            ORDER BY MAX(created_at) DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    mode_map = load_thread_mode_map([str(row["thread_id"]) for row in rows if row["thread_id"]])
    items = []
    for row in rows:
        thread_id = str(row["thread_id"])
        run_id = str(row["run_id"])
        mode_info = mode_map.get(thread_id, {"thread_mode": "normal", "keep_full_trace": False})
        items.append(
            {
                "thread_id": thread_id,
                "thread_url": f"/thread/{thread_id}?run={run_id}",
                "run_id": run_id,
                "event_count": int(row["event_count"] or 0),
                "tool_call_count": int(row["tool_call_count"] or 0),
                "tool_result_count": int(row["tool_result_count"] or 0),
                "started_at": row["started_at"],
                "started_ago": format_time_ago(row["started_at"]) if row["started_at"] else None,
                "last_event_at": row["last_event_at"],
                "last_event_ago": format_time_ago(row["last_event_at"]) if row["last_event_at"] else None,
                "status": "completed" if int(row["has_run_done"] or 0) > 0 else "running",
                "thread_mode": mode_info["thread_mode"],
                "keep_full_trace": mode_info["keep_full_trace"],
            }
        )

    page = (offset // limit) + 1
    return {
        "title": "Recent Traces",
        "count": len(items),
        "items": items,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total,
            "page": page,
            "has_prev": offset > 0,
            "has_next": (offset + len(items)) < total,
            "prev_offset": max(offset - limit, 0) if offset > 0 else None,
            "next_offset": (offset + limit) if (offset + len(items)) < total else None,
        },
    }


def _msg_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(str(block.get("text", "")))
        return "".join(texts)
    return str(content or "")


def _load_checkpoint_events(thread_id: str, limit: int) -> tuple[list[dict], dict[str, int]]:
    with sqlite3.connect(str(DB_PATH)) as conn:
        row = conn.execute(
            "SELECT checkpoint FROM checkpoints WHERE thread_id=? ORDER BY rowid DESC LIMIT 1",
            (thread_id,),
        ).fetchone()
    if not row:
        return [], {}

    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    checkpoint_blob = row[0]
    serde = JsonPlusSerializer()
    checkpoint = serde.loads_typed(("msgpack", checkpoint_blob))
    messages = checkpoint.get("channel_values", {}).get("messages", [])

    call_name_by_id: dict[str, str] = {}
    events: list[dict] = []
    counts: dict[str, int] = {}
    seq = 1
    for msg in messages:
        cls = msg.__class__.__name__
        if cls == "AIMessage":
            text = _msg_text(getattr(msg, "content", ""))
            if text.strip():
                payload = {"content": text, "_seq": seq, "_run_id": "checkpoint"}
                events.append(
                    {
                        "seq": seq,
                        "event_type": "text",
                        "payload": payload,
                        "message_id": None,
                        "created_at": None,
                        "created_ago": None,
                    }
                )
                counts["text"] = counts.get("text", 0) + 1
                seq += 1
            for call in getattr(msg, "tool_calls", None) or []:
                call_id = str(call.get("id", ""))
                name = str(call.get("name", "tool"))
                if call_id:
                    call_name_by_id[call_id] = name
                payload = {"id": call_id, "name": name, "args": call.get("args", {}), "_seq": seq, "_run_id": "checkpoint"}
                events.append(
                    {
                        "seq": seq,
                        "event_type": "tool_call",
                        "payload": payload,
                        "message_id": None,
                        "created_at": None,
                        "created_ago": None,
                    }
                )
                counts["tool_call"] = counts.get("tool_call", 0) + 1
                seq += 1
        elif cls == "ToolMessage":
            tool_call_id = str(getattr(msg, "tool_call_id", "") or "")
            name = call_name_by_id.get(tool_call_id, "tool")
            payload = {
                "tool_call_id": tool_call_id,
                "name": name,
                "content": _msg_text(getattr(msg, "content", "")),
                "_seq": seq,
                "_run_id": "checkpoint",
            }
            events.append(
                {
                    "seq": seq,
                    "event_type": "tool_result",
                    "payload": payload,
                    "message_id": None,
                    "created_at": None,
                    "created_ago": None,
                }
            )
            counts["tool_result"] = counts.get("tool_result", 0) + 1
            seq += 1
    # @@@checkpoint-trace-fallback - convert latest checkpoint messages into
    # event-like rows so thread trace still renders when run_events are absent.
    if limit > 0:
        events = events[-limit:]
    return events, counts


def load_thread_trace_payload(thread_id: str, run_id: str | None = None, limit: int = 2000) -> dict:
    """Load persisted trace bound to thread/run (not session)."""
    run_candidates = load_run_candidates(thread_id, limit=50)
    if not run_id:
        run_id = run_candidates[0]["run_id"] if run_candidates else None

    if run_id == "checkpoint":
        checkpoint_events, checkpoint_counts = _load_checkpoint_events(thread_id, limit)
        return {
            "thread_id": thread_id,
            "run_id": "checkpoint",
            "run_candidates": [],
            "event_count": len(checkpoint_events),
            "events": checkpoint_events,
            "event_type_counts": checkpoint_counts,
        }

    if not run_id:
        checkpoint_events, checkpoint_counts = _load_checkpoint_events(thread_id, limit)
        if checkpoint_events:
            return {
                "thread_id": thread_id,
                "run_id": "checkpoint",
                "run_candidates": [],
                "event_count": len(checkpoint_events),
                "events": checkpoint_events,
                "event_type_counts": checkpoint_counts,
            }
        return {
            "thread_id": thread_id,
            "run_id": None,
            "run_candidates": run_candidates,
            "event_count": 0,
            "events": [],
            "event_type_counts": {},
        }

    if not RUN_EVENT_DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Trace database not found")

    with sqlite3.connect(str(RUN_EVENT_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT seq, event_type, data, message_id, created_at
            FROM run_events
            WHERE thread_id = ? AND run_id = ?
            ORDER BY seq ASC
            LIMIT ?
            """,
            (thread_id, run_id, limit),
        ).fetchall()

    events: list[dict] = []
    event_type_counts: dict[str, int] = {}
    for row in rows:
        event_type = row["event_type"]
        try:
            payload = json.loads(row["data"]) if row["data"] else {}
        except json.JSONDecodeError:
            payload = {"raw": row["data"]}
        event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
        events.append(
            {
                "seq": int(row["seq"]),
                "event_type": event_type,
                "payload": payload,
                "message_id": row["message_id"],
                "created_at": row["created_at"],
                "created_ago": format_time_ago(row["created_at"]) if row["created_at"] else None,
            }
        )

    return {
        "thread_id": thread_id,
        "run_id": run_id,
        "run_candidates": run_candidates,
        "event_count": len(events),
        "events": events,
        "event_type_counts": event_type_counts,
    }


@router.get("/threads")
def list_threads(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: sqlite3.Connection = Depends(get_db),
):
    total_row = db.execute(
        """
        SELECT COUNT(DISTINCT thread_id) AS total_threads
        FROM chat_sessions
        """
    ).fetchone()
    session_total = int(total_row["total_threads"] if total_row else 0)
    rows = db.execute(
        """
        SELECT
            cs.thread_id,
            COUNT(DISTINCT cs.chat_session_id) as session_count,
            MAX(cs.last_active_at) as last_active,
            sl.lease_id,
            sl.provider_name,
            sl.desired_state,
            sl.observed_state,
            sl.current_instance_id
        FROM chat_sessions cs
        LEFT JOIN sandbox_leases sl ON cs.lease_id = sl.lease_id
        GROUP BY cs.thread_id
        ORDER BY MAX(cs.last_active_at) DESC
    """,
    ).fetchall()

    seen_thread_ids = {str(row["thread_id"]) for row in rows if row["thread_id"]}
    checkpoint_threads = [row for row in _list_running_eval_checkpoint_threads() if row["thread_id"] not in seen_thread_ids]
    total = session_total + len(checkpoint_threads)

    items = []
    for row in rows:
        items.append(
            {
                "thread_id": row["thread_id"],
                "thread_url": f"/thread/{row['thread_id']}",
                "thread_mode": "normal",
                "keep_full_trace": False,
                "session_count": row["session_count"],
                "last_active": row["last_active"],
                "last_active_ago": format_time_ago(row["last_active"]),
                "lease": {
                    "lease_id": row["lease_id"],
                    "lease_url": f"/lease/{row['lease_id']}" if row["lease_id"] else None,
                    "provider": row["provider_name"],
                    "instance_id": row["current_instance_id"],
                },
                "state_badge": make_badge(row["desired_state"], row["observed_state"]),
            }
        )

    for row in checkpoint_threads:
        items.append(
            {
                "thread_id": row["thread_id"],
                "thread_url": f"/thread/{row['thread_id']}",
                "thread_mode": "evaluation",
                "keep_full_trace": True,
                "session_count": 0,
                "last_active": row["last_active"],
                "last_active_ago": format_time_ago(row["last_active"]) if row["last_active"] else "just now",
                "lease": {
                    "lease_id": None,
                    "lease_url": None,
                    "provider": None,
                    "instance_id": None,
                },
                "state_badge": {
                    "desired": "running",
                    "observed": "running",
                    "converged": True,
                    "color": "green",
                    "text": "running",
                },
            }
        )

    items.sort(key=lambda item: str(item.get("last_active") or ""), reverse=True)
    items = items[offset : offset + limit]

    # @@@threads-pagination-mode-map - now that session threads and checkpoint threads share one sort order,
    # load thread mode only for the current page instead of pre-paginating twice.
    mode_map = load_thread_mode_map(
        [str(item["thread_id"]) for item in items if item.get("thread_mode") != "evaluation" and item.get("thread_id")]
    )
    for item in items:
        if item.get("thread_mode") == "evaluation":
            continue
        mode_info = mode_map.get(str(item["thread_id"]), {"thread_mode": "normal", "keep_full_trace": False})
        item["thread_mode"] = mode_info["thread_mode"]
        item["keep_full_trace"] = mode_info["keep_full_trace"]

    page = (offset // limit) + 1
    return {
        "title": "All Threads",
        "count": len(items),
        "items": items,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total,
            "page": page,
            "has_prev": offset > 0,
            "has_next": (offset + len(items)) < total,
            "prev_offset": max(offset - limit, 0) if offset > 0 else None,
            "next_offset": (offset + limit) if (offset + len(items)) < total else None,
        },
    }


@router.get("/thread/{thread_id}")
def get_thread(thread_id: str, db: sqlite3.Connection = Depends(get_db)):
    sessions = db.execute(
        """
        SELECT
            cs.chat_session_id,
            cs.status,
            cs.started_at,
            cs.ended_at,
            cs.close_reason,
            cs.lease_id,
            sl.provider_name,
            sl.desired_state,
            sl.observed_state,
            sl.current_instance_id,
            sl.last_error
        FROM chat_sessions cs
        LEFT JOIN sandbox_leases sl ON cs.lease_id = sl.lease_id
        WHERE cs.thread_id = ?
        ORDER BY cs.started_at DESC
    """,
        (thread_id,),
    ).fetchall()

    session_items = []
    lease_ids = set()

    for s in sessions:
        if s["lease_id"]:
            lease_ids.add(s["lease_id"])

        session_items.append(
            {
                "session_id": s["chat_session_id"],
                "session_url": f"/session/{s['chat_session_id']}",
                "status": s["status"],
                "started_at": s["started_at"],
                "started_ago": format_time_ago(s["started_at"]),
                "ended_at": s["ended_at"],
                "ended_ago": format_time_ago(s["ended_at"]) if s["ended_at"] else None,
                "close_reason": s["close_reason"],
                "lease": {
                    "lease_id": s["lease_id"],
                    "lease_url": f"/lease/{s['lease_id']}" if s["lease_id"] else None,
                    "provider": s["provider_name"],
                    "instance_id": s["current_instance_id"],
                },
                "state_badge": make_badge(s["desired_state"], s["observed_state"]),
                "error": s["last_error"],
            }
        )

    mode_info = load_thread_mode(thread_id)
    return {
        "thread_id": thread_id,
        "thread_mode": mode_info["thread_mode"],
        "keep_full_trace": mode_info["keep_full_trace"],
        "breadcrumb": [
            {"label": "Threads", "url": "/threads"},
            {"label": thread_id[:8], "url": f"/thread/{thread_id}"},
        ],
        "sessions": {"title": "Sessions", "count": len(session_items), "items": session_items},
        "related_leases": {
            "title": "Related Leases",
            "items": [{"lease_id": lid, "lease_url": f"/lease/{lid}"} for lid in lease_ids],
        },
    }


@router.get("/traces")
def get_traces(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    return list_trace_runs(offset=offset, limit=limit)


@router.get("/thread/{thread_id}/conversation")
async def get_thread_conversation(thread_id: str, request: Request):
    """Return raw serialized LangChain messages for monitor conversation view."""
    from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
    from backend.web.utils.serializers import serialize_message
    from sandbox.thread_context import set_current_thread_id

    app = request.app
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    set_current_thread_id(thread_id)
    state = await agent.agent.aget_state({"configurable": {"thread_id": thread_id}})
    values = getattr(state, "values", {}) if state else {}
    messages = values.get("messages", []) if isinstance(values, dict) else []
    return {
        "thread_id": thread_id,
        "count": len(messages),
        "messages": [serialize_message(msg) for msg in messages],
    }


@router.post("/evaluations")
async def create_evaluation(payload: EvaluationCreateRequest, request: Request):
    """Create one evaluation job and run SWE-bench slice in backend runner."""
    _ensure_evaluation_tables()
    app = request.app
    now = datetime.now().isoformat()
    evaluation_id = f"eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            """
            INSERT INTO evaluation_jobs (
                evaluation_id, dataset, split, start_idx, slice_count, prompt_profile,
                timeout_sec, recursion_limit, sandbox, cwd, arm, status, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)
            """,
            (
                evaluation_id,
                payload.dataset,
                payload.split,
                payload.start,
                payload.count,
                payload.prompt_profile,
                payload.timeout_sec,
                payload.recursion_limit,
                payload.sandbox,
                payload.cwd,
                payload.arm,
                "runner=direct (backend subprocess)",
                now,
                now,
            ),
        )
        conn.commit()

    tasks = _ensure_eval_task_map(app)
    task = asyncio.create_task(_run_evaluation_job(evaluation_id, payload))
    tasks[evaluation_id] = task

    def _cleanup_task(done_task: asyncio.Task) -> None:
        task_map = _ensure_eval_task_map(app)
        task_map.pop(evaluation_id, None)
        _ = done_task

    task.add_done_callback(_cleanup_task)

    return {
        "evaluation_id": evaluation_id,
        "status": "running",
        "count": payload.count,
        "dataset": payload.dataset,
        "split": payload.split,
        "start": payload.start,
        "runner": "backend_subprocess",
        "threads": [],
    }


@router.get("/evaluations")
def list_evaluations(
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    request: Request = None,
):
    _ensure_evaluation_tables()
    _backfill_evaluations_from_artifacts(request.app if request else None)
    running_jobs = set()
    pending_status_updates: dict[str, tuple[str, str]] = {}
    if request:
        tasks = _ensure_eval_task_map(request.app)
        running_jobs = {evaluation_id for evaluation_id, task in tasks.items() if not task.done()}
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        total_jobs = int(conn.execute("SELECT COUNT(*) AS n FROM evaluation_jobs").fetchone()["n"])
        jobs = conn.execute(
            """
            SELECT evaluation_id, dataset, split, start_idx, slice_count, prompt_profile, timeout_sec,
                   recursion_limit, sandbox, cwd, arm, status, notes, created_at, updated_at
            FROM evaluation_jobs
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        items = []
        for row in jobs:
            notes = row["notes"] or ""
            status = str(row["status"] or "pending")
            # @@@monitor-eval-orphan-reconcile - if backend restarted and task
            # map no longer tracks a running job, mark it error to avoid
            # permanent fake-running rows.
            if status == "running" and row["evaluation_id"] not in running_jobs:
                if _is_eval_runner_alive(str(row["evaluation_id"]), notes):
                    if "runner_lost_pid_alive:" not in notes:
                        notes = f"{notes} | runner_lost_pid_alive: runner process still alive".strip(" |")
                    pending_status_updates[str(row["evaluation_id"])] = ("running", notes)
                    status = "running"
                else:
                    if "runner_lost:" not in notes:
                        notes = f"{notes} | runner_lost: task not active after restart".strip(" |")
                    pending_status_updates[str(row["evaluation_id"])] = ("error", notes)
                    status = "error"

            score = _load_evaluation_score(
                evaluation_id=str(row["evaluation_id"]),
                cwd=row["cwd"],
                notes=notes,
            )
            # @@@eval-status-recover-pid - historical rows may already be marked error after backend restart;
            # if score is still pending and runner pid is still alive, recover status back to running.
            if status == "error" and not bool(score.get("scored")):
                if _is_eval_runner_alive(str(row["evaluation_id"]), notes):
                    if "runner_recovered_pid_alive:" not in notes:
                        notes = f"{notes} | runner_recovered_pid_alive: runner process still alive".strip(" |")
                    pending_status_updates[str(row["evaluation_id"])] = ("running", notes)
                    status = "running"
            inserted = _backfill_eval_threads_from_score(
                conn,
                evaluation_id=str(row["evaluation_id"]),
                start_idx=int(row["start_idx"] or 0),
                created_at=row["created_at"],
                score=score,
            )
            if inserted > 0:
                conn.commit()

            threads = conn.execute(
                """
                SELECT thread_id
                FROM evaluation_job_threads
                WHERE evaluation_id = ?
                """,
                (row["evaluation_id"],),
            ).fetchall()
            mapped_threads = len(threads)
            threads_total = mapped_threads
            if row["evaluation_id"] in running_jobs:
                status = "running"
            running_count = threads_total if status == "running" else 0
            threads_done = max(threads_total - running_count, 0)
            threads_started = running_count
            live_session_progress = _load_live_eval_session_progress(str(row["evaluation_id"]), row["cwd"], notes)
            if status == "running":
                # @@@eval-live-progress-from-checkpoints - thread rows are
                # ingested after runner exits; use live checkpoint thread ids
                # for in-flight progress.
                running_count = max(running_count, _count_live_eval_threads(str(row["evaluation_id"])))
                threads_total = max(threads_total, running_count)
                if live_session_progress:
                    threads_total = max(threads_total, int(live_session_progress["total"]))
                    running_count = max(0, min(threads_total, int(live_session_progress["running"])))
                    threads_done = max(0, min(threads_total, int(live_session_progress["done"])))
                    threads_started = max(0, min(threads_total, threads_done + running_count))
                else:
                    threads_done = max(threads_total - running_count, 0)
                    threads_started = running_count
            elif threads_total == 0 and int(score.get("active_trace_threads") or 0) > 0:
                threads_total = int(score.get("active_trace_threads") or 0)
                threads_done = max(threads_total - running_count, 0)
                threads_started = running_count
            # @@@eval-progress-source - while running, monitor may only have checkpoint-derived started thread count
            # (no persisted thread rows yet), so "running" is an estimate and should be labeled accordingly in UI.
            progress_source = "thread_rows"
            if status == "running" and mapped_threads == 0:
                progress_source = "session_rows" if live_session_progress else "checkpoint_estimate"
            status = _derive_evaluation_status(status, score)
            if status != str(row["status"] or "pending"):
                pending_status_updates[str(row["evaluation_id"])] = (status, notes)
            items.append(
                {
                    "evaluation_id": row["evaluation_id"],
                    "evaluation_url": f"/evaluation/{row['evaluation_id']}",
                    "dataset": row["dataset"],
                    "split": row["split"],
                    "start_idx": int(row["start_idx"] or 0),
                    "slice_count": int(row["slice_count"] or 0),
                    "prompt_profile": row["prompt_profile"],
                    "timeout_sec": int(row["timeout_sec"] or 0),
                    "recursion_limit": int(row["recursion_limit"] or 0),
                    "status": status,
                    "sandbox": row["sandbox"],
                    "threads_total": threads_total,
                    "threads_running": running_count,
                    "threads_done": threads_done,
                    "threads_started": threads_started,
                    "progress_source": progress_source,
                    "notes": notes,
                    "score": score,
                    "created_at": row["created_at"],
                    "created_ago": format_time_ago(row["created_at"]) if row["created_at"] else None,
                    "updated_at": row["updated_at"],
                    "updated_ago": format_time_ago(row["updated_at"]) if row["updated_at"] else None,
                }
            )
    for evaluation_id, (status, notes) in pending_status_updates.items():
        try:
            _update_evaluation_job_status(evaluation_id, status, notes)
        except sqlite3.OperationalError as exc:
            # @@@eval-status-update-lock - avoid surfacing sqlite lock as 500 in list API; keep response serving and retry next poll.
            print(f"[monitor] status update skipped due to sqlite lock: evaluation_id={evaluation_id} error={exc}", flush=True)
    page = (offset // limit) + 1
    return {
        "title": "Evaluations",
        "count": len(items),
        "total": total_jobs,
        "items": items,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total_jobs,
            "page": page,
            "has_prev": offset > 0,
            "has_next": (offset + len(items)) < total_jobs,
            "prev_offset": max(offset - limit, 0) if offset > 0 else None,
            "next_offset": (offset + limit) if (offset + len(items)) < total_jobs else None,
        },
    }


@router.get("/evaluation/runs")
def list_evaluation_runs(limit: int = 30, request: Request = None):
    """Backward-compatible endpoint, now returns evaluation jobs."""
    return list_evaluations(limit=limit, request=request)


@router.get("/evaluation/{evaluation_id}")
def get_evaluation_detail(evaluation_id: str, request: Request, db: sqlite3.Connection = Depends(get_db)):
    _ensure_evaluation_tables()
    running_jobs = set()
    if request:
        tasks = _ensure_eval_task_map(request.app)
        running_jobs = {job_id for job_id, task in tasks.items() if not task.done()}
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        job = conn.execute(
            """
            SELECT evaluation_id, dataset, split, start_idx, slice_count, prompt_profile, timeout_sec,
                   recursion_limit, sandbox, cwd, arm, status, notes, created_at, updated_at
            FROM evaluation_jobs
            WHERE evaluation_id = ?
            LIMIT 1
            """,
            (evaluation_id,),
        ).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="evaluation not found")
        rows = conn.execute(
            """
            SELECT thread_id, run_id, start_idx, item_index, created_at
            FROM evaluation_job_threads
            WHERE evaluation_id = ?
            ORDER BY item_index ASC
            """,
            (evaluation_id,),
        ).fetchall()

    status = str(job["status"] or "pending")
    notes = job["notes"] or ""
    if status == "running" and evaluation_id not in running_jobs:
        if _is_eval_runner_alive(evaluation_id, notes):
            if "runner_lost_pid_alive:" not in notes:
                notes = f"{notes} | runner_lost_pid_alive: runner process still alive".strip(" |")
            _update_evaluation_job_status(evaluation_id, "running", notes)
            status = "running"
        else:
            if "runner_lost:" not in notes:
                notes = f"{notes} | runner_lost: task not active after restart".strip(" |")
            _update_evaluation_job_status(evaluation_id, "error", notes)
            status = "error"
    if evaluation_id in running_jobs:
        status = "running"
    score = _load_evaluation_score(
        evaluation_id=evaluation_id,
        cwd=job["cwd"],
        notes=notes,
    )
    # @@@eval-status-recover-pid - recover stale error rows to running when runner pid is still alive and score has not closed.
    if status == "error" and not bool(score.get("scored")):
        if _is_eval_runner_alive(evaluation_id, notes):
            if "runner_recovered_pid_alive:" not in notes:
                notes = f"{notes} | runner_recovered_pid_alive: runner process still alive".strip(" |")
            _update_evaluation_job_status(evaluation_id, "running", notes)
            status = "running"
    if len(rows) == 0:
        with sqlite3.connect(str(DB_PATH)) as conn:
            inserted = _backfill_eval_threads_from_score(
                conn,
                evaluation_id=evaluation_id,
                start_idx=int(job["start_idx"] or 0),
                created_at=job["created_at"],
                score=score,
            )
            if inserted > 0:
                conn.commit()
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT thread_id, run_id, start_idx, item_index, created_at
                    FROM evaluation_job_threads
                    WHERE evaluation_id = ?
                    ORDER BY item_index ASC
                    """,
                    (evaluation_id,),
                ).fetchall()
    status = _derive_evaluation_status(status, score)
    if status != str(job["status"] or "pending"):
        _update_evaluation_job_status(evaluation_id, status, notes)
    thread_items = []
    mapped_threads = len(rows)
    running_count = 0
    done_count = 0
    live_session_progress = _load_live_eval_session_progress(evaluation_id, job["cwd"], notes)
    live_sessions = _load_live_eval_sessions(evaluation_id, job["cwd"], notes)
    live_session_by_thread = {str(s["thread_id"]): s for s in live_sessions}
    row_by_thread = {str(r["thread_id"]): r for r in rows}
    merged_thread_ids: list[str] = []
    for s in live_sessions:
        tid = str(s["thread_id"])
        if tid not in merged_thread_ids:
            merged_thread_ids.append(tid)
    for r in rows:
        tid = str(r["thread_id"])
        if tid not in merged_thread_ids:
            merged_thread_ids.append(tid)
    for tid in _list_checkpoint_threads_for_evaluation(evaluation_id):
        if tid not in merged_thread_ids:
            merged_thread_ids.append(tid)

    # @@@eval-detail-thread-source-unify - running phase has live sessions before evaluation_job_threads is persisted;
    # build detail rows from merged(live sessions, persisted mappings) so "count" and table rows stay consistent.
    start_idx_base = int(job["start_idx"] or 0)
    for idx, thread_id in enumerate(merged_thread_ids):
        row = row_by_thread.get(thread_id)
        live_session = live_session_by_thread.get(thread_id)
        session = _load_latest_session(db, thread_id)
        session_row = session if session else None
        if not session_row and live_session:
            session_row = {
                "chat_session_id": live_session["chat_session_id"],
                "status": live_session["status"],
                "started_at": live_session["started_at"],
                "last_active_at": live_session["last_active_at"],
            }
        run = _load_run_stats(thread_id, row["run_id"] if row else evaluation_id)
        running = bool(status == "running" and session and session["status"] == "active")
        if not session and live_session:
            running = bool(status == "running" and str(live_session["status"]) == "active")
        if running:
            running_count += 1
        elif session_row and session_row["status"] and session_row["status"] != "active":
            done_count += 1
        thread_items.append(
            {
                "thread_id": thread_id,
                "thread_url": f"/thread/{thread_id}",
                "start_idx": int(row["start_idx"] or (start_idx_base + idx)) if row else (start_idx_base + idx),
                "item_index": int(row["item_index"] or idx) if row else idx,
                "created_at": (row["created_at"] if row else (live_session["started_at"] if live_session else None)),
                "created_ago": (
                    format_time_ago(row["created_at"])
                    if row and row["created_at"]
                    else (format_time_ago(live_session["started_at"]) if live_session and live_session["started_at"] else None)
                ),
                "run": run,
                "session": {
                    "session_id": session_row["chat_session_id"] if session_row else None,
                    "session_url": f"/session/{session_row['chat_session_id']}" if session else None,
                    "status": session_row["status"] if session_row else None,
                    "started_ago": format_time_ago(session_row["started_at"]) if session_row and session_row["started_at"] else None,
                    "last_active_ago": format_time_ago(session_row["last_active_at"])
                    if session_row and session_row["last_active_at"]
                    else None,
                },
                "status": "running"
                if running
                else (session_row["status"] if session_row else ("running" if status == "running" else "idle")),
                "running": running,
            }
        )

    total = len(thread_items)
    if status == "running":
        # @@@eval-live-progress-from-checkpoints - evaluation thread mappings
        # are persisted at the end, so derive interim running count from live
        # checkpoint data.
        checkpoint_started = _count_live_eval_threads(evaluation_id)
        running_count = max(running_count, checkpoint_started)
        total = max(total, running_count)
        if live_session_progress:
            total = max(total, int(live_session_progress["total"]))
            if mapped_threads == 0:
                running_count = max(0, min(total, int(live_session_progress["running"])))
                done_count = max(0, min(total, int(live_session_progress["done"])))
            else:
                running_count = max(running_count, min(total, int(live_session_progress["running"])))
                done_count = max(done_count, min(total, int(live_session_progress["done"])))
    threads_done = max(total - running_count, 0)
    if live_session_progress:
        threads_done = max(threads_done, min(total, int(live_session_progress["done"])))
    threads_started = max(0, min(total, threads_done + running_count))
    # @@@eval-progress-source - when no persisted thread mapping exists yet, running count is checkpoint-derived
    # "started thread" estimate and must not be presented as exact in-flight count.
    progress_source = "thread_rows"
    if status == "running" and mapped_threads == 0:
        progress_source = "session_rows" if live_session_progress else "checkpoint_estimate"

    return {
        "evaluation_id": evaluation_id,
        "breadcrumb": [
            {"label": "Evaluation", "url": "/evaluation"},
            {"label": evaluation_id, "url": f"/evaluation/{evaluation_id}"},
        ],
        "info": {
            "dataset": job["dataset"],
            "split": job["split"],
            "start_idx": int(job["start_idx"] or 0),
            "slice_count": int(job["slice_count"] or 0),
            "prompt_profile": job["prompt_profile"],
            "timeout_sec": int(job["timeout_sec"] or 0),
            "recursion_limit": int(job["recursion_limit"] or 0),
            "sandbox": job["sandbox"],
            "cwd": job["cwd"],
            "arm": job["arm"],
            "status": status,
            "notes": notes,
            "created_at": job["created_at"],
            "created_ago": format_time_ago(job["created_at"]) if job["created_at"] else None,
            "updated_at": job["updated_at"],
            "updated_ago": format_time_ago(job["updated_at"]) if job["updated_at"] else None,
            "threads_total": total,
            "threads_running": running_count,
            "threads_done": threads_done,
            "threads_started": threads_started,
            "progress_source": progress_source,
            "score": score,
            "operator_surface": build_evaluation_operator_surface(
                status=status,
                notes=notes,
                score=score,
                threads_total=total,
                threads_running=running_count,
                threads_done=threads_done,
            ),
        },
        "threads": {"title": "Evaluation Threads", "count": total, "items": thread_items},
    }


@router.get("/session/{session_id}")
def get_session(session_id: str, db: sqlite3.Connection = Depends(get_db)):
    session = db.execute(
        """
        SELECT
            cs.chat_session_id,
            cs.thread_id,
            cs.terminal_id,
            cs.lease_id,
            cs.status,
            cs.started_at,
            cs.last_active_at,
            cs.ended_at,
            cs.close_reason,
            sl.provider_name,
            sl.desired_state,
            sl.observed_state,
            sl.current_instance_id,
            sl.last_error
        FROM chat_sessions cs
        LEFT JOIN sandbox_leases sl ON cs.lease_id = sl.lease_id
        WHERE cs.chat_session_id = ?
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "thread_id": session["thread_id"],
        "thread_url": f"/thread/{session['thread_id']}",
        "breadcrumb": [
            {"label": "Threads", "url": "/threads"},
            {"label": session["thread_id"][:8], "url": f"/thread/{session['thread_id']}"},
            {"label": session_id[:8], "url": f"/session/{session_id}"},
        ],
        "info": {
            "status": session["status"],
            "terminal_id": session["terminal_id"],
            "lease_id": session["lease_id"],
            "provider": session["provider_name"],
            "instance_id": session["current_instance_id"],
            "started_at": session["started_at"],
            "started_ago": format_time_ago(session["started_at"]),
            "last_active_at": session["last_active_at"],
            "last_active_ago": format_time_ago(session["last_active_at"]),
            "ended_at": session["ended_at"],
            "ended_ago": format_time_ago(session["ended_at"]) if session["ended_at"] else None,
            "close_reason": session["close_reason"],
            "error": session["last_error"],
            "state_badge": make_badge(session["desired_state"], session["observed_state"]),
        },
    }


@router.get("/thread/{thread_id}/trace")
def get_thread_trace(thread_id: str, run_id: str | None = None, limit: int = 2000):
    """Canonical trace endpoint: trace belongs to thread/run."""
    return load_thread_trace_payload(thread_id=thread_id, run_id=run_id, limit=limit)


@router.get("/leases")
def list_leases():
    from backend.web.services import monitor_service

    return monitor_service.list_leases()


@router.get("/lease/{lease_id}")
def get_lease(lease_id: str):
    from backend.web.services import monitor_service

    try:
        return monitor_service.get_lease(lease_id)
    except KeyError as exc:
        detail = exc.args[0] if exc.args else "Lease not found"
        raise HTTPException(status_code=404, detail=detail) from exc


@router.get("/diverged")
def list_diverged(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("""
        SELECT
            sl.lease_id,
            sl.provider_name,
            sl.desired_state,
            sl.observed_state,
            sl.current_instance_id,
            sl.last_error,
            sl.updated_at,
            cs.thread_id,
            CAST((julianday('now', 'localtime') - julianday(sl.updated_at)) * 24 AS INTEGER) as hours_diverged
        FROM sandbox_leases sl
        LEFT JOIN chat_sessions cs ON sl.lease_id = cs.lease_id
        WHERE sl.desired_state != sl.observed_state
        ORDER BY hours_diverged DESC
    """).fetchall()

    items = []
    for row in rows:
        items.append(
            {
                "lease_id": row["lease_id"],
                "lease_url": f"/lease/{row['lease_id']}",
                "provider": row["provider_name"],
                "instance_id": row["current_instance_id"],
                "thread": {
                    "thread_id": row["thread_id"],
                    "thread_url": f"/thread/{row['thread_id']}" if row["thread_id"] else None,
                    "is_orphan": not row["thread_id"],
                },
                "state_badge": {
                    "desired": row["desired_state"],
                    "observed": row["observed_state"],
                    "hours_diverged": row["hours_diverged"],
                    "color": "red" if row["hours_diverged"] > 24 else "yellow",
                },
                "error": row["last_error"],
            }
        )

    return {
        "title": "Diverged Leases",
        "description": "Leases where desired_state ≠ observed_state",
        "count": len(items),
        "items": items,
    }


@router.get("/events")
def list_events(limit: int = 100, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        """
        SELECT le.event_id, le.lease_id, le.event_type, le.source,
               le.payload_json, le.error, le.created_at,
               sl.provider_name
        FROM lease_events le
        LEFT JOIN sandbox_leases sl ON le.lease_id = sl.lease_id
        ORDER BY le.created_at DESC
        LIMIT ?
    """,
        (limit,),
    ).fetchall()

    items = []
    for row in rows:
        items.append(
            {
                "event_id": row["event_id"],
                "event_url": f"/event/{row['event_id']}",
                "event_type": row["event_type"],
                "source": row["source"],
                "provider": row["provider_name"],
                "lease": {
                    "lease_id": row["lease_id"],
                    "lease_url": f"/lease/{row['lease_id']}" if row["lease_id"] else None,
                },
                "error": row["error"],
                "created_at": row["created_at"],
                "created_ago": format_time_ago(row["created_at"]),
            }
        )

    return {
        "title": "Lease Events",
        "description": "Audit log of all lease lifecycle operations",
        "count": len(items),
        "items": items,
    }


@router.get("/event/{event_id}")
def get_event(event_id: str, db: sqlite3.Connection = Depends(get_db)):
    event = db.execute(
        """
        SELECT le.*, sl.provider_name
        FROM lease_events le
        LEFT JOIN sandbox_leases sl ON le.lease_id = sl.lease_id
        WHERE le.event_id = ?
    """,
        (event_id,),
    ).fetchone()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    payload = json.loads(event["payload_json"]) if event["payload_json"] else {}

    return {
        "event_id": event_id,
        "breadcrumb": [
            {"label": "Events", "url": "/events"},
            {"label": event["event_type"], "url": f"/event/{event_id}"},
        ],
        "info": {
            "event_type": event["event_type"],
            "source": event["source"],
            "provider": event["provider_name"],
            "created_at": event["created_at"],
            "created_ago": format_time_ago(event["created_at"]),
        },
        "related_lease": {
            "lease_id": event["lease_id"],
            "lease_url": f"/lease/{event['lease_id']}" if event["lease_id"] else None,
        },
        "error": event["error"],
        "payload": payload,
    }
