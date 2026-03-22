"""Agent Registry — SQLite-backed agent_id -> thread_id mapping.

@@@id-based — all lookups use agent_id, never name.
Name is stored for display only.
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentEntry:
    agent_id: str
    name: str
    thread_id: str
    status: str
    parent_agent_id: str | None = None
    subagent_type: str | None = None


class AgentRegistry:
    """SQLite-backed registry mapping agent_ids to thread IDs.

    Persisted at ~/.leon/agent_registry.db
    """

    DEFAULT_DB_PATH = Path.home() / ".leon" / "agent_registry.db"

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or self.DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    parent_agent_id TEXT,
                    subagent_type TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_thread ON agents(thread_id)")
            conn.commit()

    async def register(self, entry: AgentEntry) -> None:
        async with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO agents "
                    "(agent_id, name, thread_id, status, parent_agent_id, subagent_type) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        entry.agent_id,
                        entry.name,
                        entry.thread_id,
                        entry.status,
                        entry.parent_agent_id,
                        entry.subagent_type,
                    ),
                )
                conn.commit()

    async def get_by_id(self, agent_id: str) -> AgentEntry | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT agent_id, name, thread_id, status, parent_agent_id, subagent_type "
                "FROM agents WHERE agent_id=?",
                (agent_id,),
            ).fetchone()
        if row is None:
            return None
        return AgentEntry(
            agent_id=row[0],
            name=row[1],
            thread_id=row[2],
            status=row[3],
            parent_agent_id=row[4],
            subagent_type=row[5],
        )

    async def update_status(self, agent_id: str, status: str) -> None:
        async with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "UPDATE agents SET status=? WHERE agent_id=?",
                    (status, agent_id),
                )
                conn.commit()

    async def list_running(self) -> list[AgentEntry]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT agent_id, name, thread_id, status, parent_agent_id, subagent_type "
                "FROM agents WHERE status='running'"
            ).fetchall()
        return [
            AgentEntry(
                agent_id=r[0],
                name=r[1],
                thread_id=r[2],
                status=r[3],
                parent_agent_id=r[4],
                subagent_type=r[5],
            )
            for r in rows
        ]
