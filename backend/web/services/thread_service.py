"""Thread management service."""

import sqlite3
from typing import Any

from backend.web.core.config import DB_PATH
from sandbox.config import DEFAULT_DB_PATH as SANDBOX_DB_PATH
from storage.providers.sqlite.kernel import connect_sqlite


def list_threads_from_db() -> list[dict[str, Any]]:
    """List threads with preview and updated_at extracted from checkpoint blobs."""
    thread_ids: set[str] = set()
    thread_meta: dict[str, dict[str, Any]] = {}  # thread_id -> {preview, updated_at}

    if DB_PATH.exists():
        with connect_sqlite(DB_PATH, row_factory=sqlite3.Row) as conn:
            existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "checkpoints" in existing:
                rows = conn.execute("SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id IS NOT NULL").fetchall()
                thread_ids.update(row["thread_id"] for row in rows if row["thread_id"])

                # Extract preview + updated_at from latest checkpoint per thread
                try:
                    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

                    serde = JsonPlusSerializer()
                    ckpt_rows = conn.execute("""
                        SELECT c.thread_id, c.type, c.checkpoint
                        FROM checkpoints c
                        INNER JOIN (
                            SELECT thread_id, MAX(checkpoint_id) as max_ckpt
                            FROM checkpoints WHERE checkpoint_ns = ''
                            GROUP BY thread_id
                        ) latest ON c.thread_id = latest.thread_id AND c.checkpoint_id = latest.max_ckpt
                        WHERE c.checkpoint_ns = ''
                    """).fetchall()
                    for tid, typ, blob in ckpt_rows:
                        try:
                            data = serde.loads_typed((typ, blob))
                            ts = data.get("ts", "")
                            msgs = data.get("channel_values", {}).get("messages", [])
                            preview = ""
                            for m in msgs:
                                if getattr(m, "type", "") == "human":
                                    preview = str(getattr(m, "content", ""))[:40]
                                    break
                            thread_meta[tid] = {"preview": preview, "updated_at": ts}
                        except Exception:
                            pass
                except ImportError:
                    pass

    if SANDBOX_DB_PATH.exists():
        with connect_sqlite(SANDBOX_DB_PATH, row_factory=sqlite3.Row) as conn:
            existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "chat_sessions" in existing:
                rows = conn.execute(
                    "SELECT DISTINCT thread_id FROM chat_sessions WHERE thread_id IS NOT NULL"
                ).fetchall()
                thread_ids.update(row["thread_id"] for row in rows if row["thread_id"])

    # Batch-load agent names from thread_config
    thread_agents: dict[str, str | None] = {}
    if DB_PATH.exists():
        with connect_sqlite(DB_PATH, row_factory=sqlite3.Row) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "thread_config" in tables:
                rows = conn.execute("SELECT thread_id, agent FROM thread_config").fetchall()
                for row in rows:
                    thread_agents[row["thread_id"]] = row["agent"]

    results = []
    for tid in sorted(thread_ids):
        # Filter out sub-agent threads (thread_id format: "subagent-{task_id}")
        if tid.startswith("subagent-"):
            continue
        meta = thread_meta.get(tid, {})
        results.append(
            {
                "thread_id": tid,
                "preview": meta.get("preview", ""),
                "updated_at": meta.get("updated_at", ""),
                "agent": thread_agents.get(tid),
            }
        )
    # Sort by updated_at descending (newest first)
    results.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return results
