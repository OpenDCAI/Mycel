"""SQLite repo for agent registry persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from config.user_paths import user_home_path


class SQLiteAgentRegistryRepo:
    DEFAULT_DB_PATH = user_home_path("agent_registry.db")

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or self.DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init_db(self) -> None:
        with self._conn() as conn:
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

    def register(self, *, agent_id: str, name: str, thread_id: str, status: str, parent_agent_id: str | None, subagent_type: str | None) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agents "
                "(agent_id, name, thread_id, status, parent_agent_id, subagent_type) "
                "VALUES (?,?,?,?,?,?)",
                (agent_id, name, thread_id, status, parent_agent_id, subagent_type),
            )
            conn.commit()

    def get_by_id(self, agent_id: str) -> tuple | None:
        with self._conn() as conn:
            return conn.execute(
                "SELECT agent_id, name, thread_id, status, parent_agent_id, subagent_type "
                "FROM agents WHERE agent_id=?",
                (agent_id,),
            ).fetchone()

    def update_status(self, agent_id: str, status: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE agents SET status=? WHERE agent_id=?", (status, agent_id))
            conn.commit()

    def list_running(self) -> list[tuple]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT agent_id, name, thread_id, status, parent_agent_id, subagent_type "
                "FROM agents WHERE status='running'"
            ).fetchall()
