"""
Sandbox Monitor API - View-Ready Endpoints

All endpoints return view-ready data that frontend can directly render.
No business logic in frontend.
"""

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from subprocess import PIPE

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.web.core.config import DB_PATH
from sandbox.db import DEFAULT_DB_PATH

router = APIRouter(prefix="/api/monitor")


def get_db():
    db = sqlite3.connect(str(DEFAULT_DB_PATH))
    db.row_factory = sqlite3.Row
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
    timeout_sec: int = Field(default=180, ge=30, le=3600)
    recursion_limit: int = Field(default=24, ge=1, le=128)
    sandbox: str = "local"
    cwd: str = "/home/ubuntu/specops0/Projects/leonai-main"
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
        "--recursion-limit",
        str(payload.recursion_limit),
        "--output-dir",
        payload.output_dir,
        "--thread-prefix",
        payload.thread_prefix,
    ]
    if not payload.run_eval:
        cmd.append("--no-eval")
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
    try:
        # @@@monitor-eval-direct-runner - evaluate by invoking SWE runner directly, not by sending a control prompt to another agent.
        proc = await asyncio.create_subprocess_exec(*command, cwd=cwd, stdout=PIPE, stderr=PIPE)
        stdout, stderr = await proc.communicate()
        stdout_path.write_bytes(stdout or b"")
        stderr_path.write_bytes(stderr or b"")
        if proc.returncode != 0:
            notes = (
                f"runner=direct rc={proc.returncode} run_dir={run_dir} "
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
            f"runner=direct rc=0 run_dir={run_dir} stdout_log={stdout_path} "
            f"stderr_log={stderr_path} threads={thread_count}"
        )
        _update_evaluation_job_status(evaluation_id, "completed", notes)
    except Exception as exc:
        notes = f"runner=direct error={exc} run_dir={run_dir} stdout_log={stdout_path} stderr_log={stderr_path}"
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
    with sqlite3.connect(str(DB_PATH)) as conn:
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
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in thread_ids)
        rows = conn.execute(
            f"""
            SELECT thread_id, thread_mode, keep_full_trace
            FROM thread_config
            WHERE thread_id IN ({placeholders})
            """,
            thread_ids,
        ).fetchall()
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


def load_run_candidates(thread_id: str, limit: int = 20) -> list[dict]:
    """List recent run_ids for a thread with basic stats."""
    run_db_path = Path.home() / ".leon" / "leon.db"
    if not run_db_path.exists():
        return []
    # @@@run-candidates - Keep selector data lightweight so session page can switch run trace quickly.
    with sqlite3.connect(str(run_db_path)) as conn:
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
    # @@@checkpoint-trace-fallback - convert latest checkpoint messages into event-like rows so thread trace still renders when run_events are absent.
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

    run_db_path = Path.home() / ".leon" / "leon.db"
    if not run_db_path.exists():
        raise HTTPException(status_code=404, detail="Trace database not found")

    with sqlite3.connect(str(run_db_path)) as conn:
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
def list_threads(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("""
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
    """).fetchall()

    mode_map = load_thread_mode_map([row["thread_id"] for row in rows if row["thread_id"]])
    items = []
    for row in rows:
        badge = make_badge(row["desired_state"], row["observed_state"])
        mode_info = mode_map.get(row["thread_id"], {"thread_mode": "normal", "keep_full_trace": False})
        items.append(
            {
                "thread_id": row["thread_id"],
                "thread_url": f"/thread/{row['thread_id']}",
                "thread_mode": mode_info["thread_mode"],
                "keep_full_trace": mode_info["keep_full_trace"],
                "session_count": row["session_count"],
                "last_active": row["last_active"],
                "last_active_ago": format_time_ago(row["last_active"]),
                "lease": {
                    "lease_id": row["lease_id"],
                    "lease_url": f"/lease/{row['lease_id']}" if row["lease_id"] else None,
                    "provider": row["provider_name"],
                    "instance_id": row["current_instance_id"],
                },
                "state_badge": badge,
            }
        )

    return {"title": "All Threads", "count": len(items), "items": items}


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
def list_evaluations(limit: int = 30, request: Request = None):
    _ensure_evaluation_tables()
    running_jobs = set()
    if request:
        tasks = _ensure_eval_task_map(request.app)
        running_jobs = {evaluation_id for evaluation_id, task in tasks.items() if not task.done()}
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        jobs = conn.execute(
            """
            SELECT evaluation_id, dataset, split, start_idx, slice_count, prompt_profile, timeout_sec,
                   recursion_limit, sandbox, cwd, arm, status, notes, created_at, updated_at
            FROM evaluation_jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        items = []
        for row in jobs:
            threads = conn.execute(
                """
                SELECT thread_id
                FROM evaluation_job_threads
                WHERE evaluation_id = ?
                """,
                (row["evaluation_id"],),
            ).fetchall()
            total = len(threads)
            status = str(row["status"] or "pending")
            if row["evaluation_id"] in running_jobs:
                status = "running"
            running_count = total if status == "running" else 0
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
                    "threads_total": total,
                    "threads_running": running_count,
                    "threads_done": max(total - running_count, 0),
                    "notes": row["notes"],
                    "created_at": row["created_at"],
                    "created_ago": format_time_ago(row["created_at"]) if row["created_at"] else None,
                    "updated_at": row["updated_at"],
                    "updated_ago": format_time_ago(row["updated_at"]) if row["updated_at"] else None,
                }
            )
    return {"title": "Evaluations", "count": len(items), "items": items}


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
    if evaluation_id in running_jobs:
        status = "running"
    thread_items = []
    running_count = 0
    for row in rows:
        thread_id = str(row["thread_id"])
        session = _load_latest_session(db, thread_id)
        run = _load_run_stats(thread_id, row["run_id"])
        running = status == "running"
        if running:
            running_count += 1
        thread_items.append(
            {
                "thread_id": thread_id,
                "thread_url": f"/thread/{thread_id}",
                "start_idx": int(row["start_idx"] or 0),
                "item_index": int(row["item_index"] or 0),
                "created_at": row["created_at"],
                "created_ago": format_time_ago(row["created_at"]) if row["created_at"] else None,
                "run": run,
                "session": {
                    "session_id": session["chat_session_id"] if session else None,
                    "session_url": f"/session/{session['chat_session_id']}" if session else None,
                    "status": session["status"] if session else None,
                    "started_ago": format_time_ago(session["started_at"]) if session and session["started_at"] else None,
                    "last_active_ago": format_time_ago(session["last_active_at"])
                    if session and session["last_active_at"]
                    else None,
                },
                "status": "running" if running else (session["status"] if session else "idle"),
                "running": running,
            }
        )

    total = len(thread_items)

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
            "notes": job["notes"],
            "created_at": job["created_at"],
            "created_ago": format_time_ago(job["created_at"]) if job["created_at"] else None,
            "updated_at": job["updated_at"],
            "updated_ago": format_time_ago(job["updated_at"]) if job["updated_at"] else None,
            "threads_total": total,
            "threads_running": running_count,
            "threads_done": max(total - running_count, 0),
        },
        "threads": {"title": "Evaluation Threads", "count": total, "items": thread_items},
    }


@router.get("/evaluation/runs")
def list_evaluation_runs(limit: int = 30, request: Request = None):
    """Backward-compatible endpoint, now returns evaluation jobs."""
    return list_evaluations(limit=limit, request=request)


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
def list_leases(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("""
        SELECT
            sl.lease_id,
            sl.provider_name,
            sl.desired_state,
            sl.observed_state,
            sl.current_instance_id,
            sl.last_error,
            sl.updated_at,
            MAX(cs.thread_id) as thread_id
        FROM sandbox_leases sl
        LEFT JOIN chat_sessions cs ON sl.lease_id = cs.lease_id
        GROUP BY sl.lease_id
        ORDER BY sl.updated_at DESC
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
                "state_badge": make_badge(row["desired_state"], row["observed_state"]),
                "error": row["last_error"],
                "updated_at": row["updated_at"],
                "updated_ago": format_time_ago(row["updated_at"]),
            }
        )

    return {"title": "All Leases", "count": len(items), "items": items}


@router.get("/lease/{lease_id}")
def get_lease(lease_id: str, db: sqlite3.Connection = Depends(get_db)):
    lease = db.execute(
        """
        SELECT * FROM sandbox_leases WHERE lease_id = ?
    """,
        (lease_id,),
    ).fetchone()

    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")

    threads = db.execute(
        """
        SELECT DISTINCT thread_id FROM chat_sessions WHERE lease_id = ?
    """,
        (lease_id,),
    ).fetchall()

    # Get lease events
    events = db.execute(
        """
        SELECT * FROM lease_events
        WHERE lease_id = ?
        ORDER BY created_at DESC
    """,
        (lease_id,),
    ).fetchall()

    badge = make_badge(lease["desired_state"], lease["observed_state"])
    badge["error"] = lease["last_error"]

    return {
        "lease_id": lease_id,
        "breadcrumb": [{"label": "Leases", "url": "/leases"}, {"label": lease_id, "url": f"/lease/{lease_id}"}],
        "info": {
            "provider": lease["provider_name"],
            "instance_id": lease["current_instance_id"],
            "created_at": lease["created_at"],
            "created_ago": format_time_ago(lease["created_at"]),
            "updated_at": lease["updated_at"],
            "updated_ago": format_time_ago(lease["updated_at"]),
        },
        "state": badge,
        "related_threads": {
            "title": "Related Threads",
            "items": [{"thread_id": t["thread_id"], "thread_url": f"/thread/{t['thread_id']}"} for t in threads],
        },
        "lease_events": {
            "title": "Lease Events",
            "count": len(events),
            "items": [
                {
                    "event_id": e["event_id"],
                    "event_url": f"/event/{e['event_id']}",
                    "event_type": e["event_type"],
                    "source": e["source"],
                    "created_at": e["created_at"],
                    "created_ago": format_time_ago(e["created_at"]),
                }
                for e in events
            ],
        },
    }


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
