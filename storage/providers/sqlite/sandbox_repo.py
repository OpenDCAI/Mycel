"""New unified repository for sandbox persistence.

This is the clean implementation that will replace inline SQL in sandbox/*.py files.
It uses explicit transaction boundaries and follows repository pattern best practices.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from sandbox.config import DEFAULT_DB_PATH
from storage.providers.sqlite.kernel import connect_sqlite


class SandboxRepository:
    """Unified repository for all sandbox persistence operations.

    Key improvements over inline SQL:
    - Explicit transaction boundaries (context manager)
    - Connection reuse within transaction
    - Consistent error handling
    - Type hints
    - Single source of truth for all sandbox persistence
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # === CONTEXT MANAGER FOR TRANSACTIONS ===

    def __enter__(self):
        """Begin transaction."""
        self._conn = connect_sqlite(self.db_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Commit or rollback transaction."""
        if self._conn is None:
            return

        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()

        self._conn.close()
        self._conn = None

    def _get_conn(self) -> sqlite3.Connection:
        """Get connection (auto-commit if not in transaction)."""
        if self._conn is not None:
            # Inside transaction context
            return self._conn
        # Auto-commit mode: create temporary connection
        return connect_sqlite(self.db_path)

    def _transaction(self):
        """Context manager for transaction handling.

        If already in transaction (via __enter__), yields existing connection.
        Otherwise, creates temporary connection with auto-commit.
        """
        if self._conn is not None:
            # Already in transaction, just yield
            yield self._conn
        else:
            # Auto-commit mode
            conn = connect_sqlite(self.db_path)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    # === TABLE MANAGEMENT ===

    def ensure_tables(self) -> None:
        """Create all sandbox tables if they don't exist."""
        conn = connect_sqlite(self.db_path)
        try:
            # Lease tables
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sandbox_leases (
                    lease_id TEXT PRIMARY KEY,
                    provider_name TEXT NOT NULL,
                    workspace_key TEXT,
                    current_instance_id TEXT,
                    instance_created_at TIMESTAMP,
                    desired_state TEXT NOT NULL DEFAULT 'running',
                    observed_state TEXT NOT NULL DEFAULT 'detached',
                    instance_status TEXT NOT NULL DEFAULT 'detached',
                    version INTEGER NOT NULL DEFAULT 0,
                    observed_at TIMESTAMP,
                    last_error TEXT,
                    needs_refresh INTEGER NOT NULL DEFAULT 0,
                    refresh_hint_at TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sandbox_instances (
                    instance_id TEXT PRIMARY KEY,
                    lease_id TEXT NOT NULL,
                    provider_session_id TEXT NOT NULL,
                    status TEXT DEFAULT 'running',
                    created_at TIMESTAMP NOT NULL,
                    last_seen_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lease_events (
                    event_id TEXT PRIMARY KEY,
                    lease_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload_json TEXT,
                    error TEXT,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lease_events_lease_created
                ON lease_events(lease_id, created_at DESC)
                """
            )

            # Terminal tables
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS abstract_terminals (
                    terminal_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    env_delta_json TEXT DEFAULT '{}',
                    state_version INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS thread_terminal_pointers (
                    thread_id TEXT PRIMARY KEY,
                    active_terminal_id TEXT NOT NULL,
                    default_terminal_id TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (active_terminal_id) REFERENCES abstract_terminals(terminal_id),
                    FOREIGN KEY (default_terminal_id) REFERENCES abstract_terminals(terminal_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_abstract_terminals_thread_created
                ON abstract_terminals(thread_id, created_at DESC)
                """
            )

            # Session tables
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    chat_session_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    terminal_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    runtime_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    idle_ttl_sec INTEGER NOT NULL,
                    max_duration_sec INTEGER NOT NULL,
                    budget_json TEXT,
                    started_at TIMESTAMP NOT NULL,
                    last_active_at TIMESTAMP NOT NULL,
                    ended_at TIMESTAMP,
                    close_reason TEXT,
                    FOREIGN KEY (terminal_id) REFERENCES abstract_terminals(terminal_id),
                    FOREIGN KEY (lease_id) REFERENCES sandbox_leases(lease_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS terminal_commands (
                    command_id TEXT PRIMARY KEY,
                    terminal_id TEXT NOT NULL,
                    chat_session_id TEXT,
                    command_line TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stdout TEXT DEFAULT '',
                    stderr TEXT DEFAULT '',
                    exit_code INTEGER,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    finished_at TIMESTAMP,
                    FOREIGN KEY (terminal_id) REFERENCES abstract_terminals(terminal_id),
                    FOREIGN KEY (chat_session_id) REFERENCES chat_sessions(chat_session_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS terminal_command_chunks (
                    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command_id TEXT NOT NULL,
                    stream TEXT NOT NULL CHECK (stream IN ('stdout', 'stderr')),
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (command_id) REFERENCES terminal_commands(command_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_terminal_command_chunks_command_order
                ON terminal_command_chunks(command_id, chunk_id)
                """
            )

            # Event tables
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_name TEXT NOT NULL,
                    instance_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT,
                    matched_lease_id TEXT,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_provider_events_created
                ON provider_events(created_at DESC)
                """
            )

            conn.commit()
        finally:
            conn.close()

    # === LEASE OPERATIONS ===

    def upsert_lease(
        self,
        lease_id: str,
        provider_name: str,
        workspace_key: str | None,
        current_instance_id: str | None,
        instance_created_at: str | None,
        desired_state: str,
        observed_state: str,
        version: int,
        observed_at: str | None,
        last_error: str | None,
        needs_refresh: int,
        refresh_hint_at: str | None,
        status: str,
        created_at: str,
        updated_at: str,
    ) -> None:
        """Insert or update lease."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO sandbox_leases (
                    lease_id, provider_name, workspace_key, current_instance_id,
                    instance_created_at, desired_state, observed_state, version,
                    observed_at, last_error, needs_refresh, refresh_hint_at,
                    status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lease_id) DO UPDATE SET
                    provider_name = excluded.provider_name,
                    workspace_key = excluded.workspace_key,
                    current_instance_id = excluded.current_instance_id,
                    instance_created_at = excluded.instance_created_at,
                    desired_state = excluded.desired_state,
                    observed_state = excluded.observed_state,
                    version = excluded.version,
                    observed_at = excluded.observed_at,
                    last_error = excluded.last_error,
                    needs_refresh = excluded.needs_refresh,
                    refresh_hint_at = excluded.refresh_hint_at,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    lease_id,
                    provider_name,
                    workspace_key,
                    current_instance_id,
                    instance_created_at,
                    desired_state,
                    observed_state,
                    version,
                    observed_at,
                    last_error,
                    needs_refresh,
                    refresh_hint_at,
                    status,
                    created_at,
                    updated_at,
                ),
            )

    def update_lease_state(
        self,
        lease_id: str,
        observed_state: str,
        version: int,
        observed_at: str,
        last_error: str | None = None,
    ) -> None:
        """Update lease observed state."""
        with self._transaction() as conn:
            conn.execute(
                """
                UPDATE sandbox_leases
                SET observed_state = ?, version = ?, observed_at = ?, last_error = ?
                WHERE lease_id = ?
                """,
                (observed_state, version, observed_at, last_error, lease_id),
            )

    def get_lease(self, lease_id: str) -> dict[str, Any] | None:
        """Get lease by ID."""
        with self._transaction() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM sandbox_leases WHERE lease_id = ?", (lease_id,)
            ).fetchone()
            return dict(row) if row else None

    def delete_lease(self, lease_id: str) -> None:
        """Delete lease."""
        with self._transaction() as conn:
            conn.execute("DELETE FROM sandbox_leases WHERE lease_id = ?", (lease_id,))

    # === INSTANCE OPERATIONS ===

    def upsert_instance(
        self,
        instance_id: str,
        lease_id: str,
        provider_session_id: str,
        status: str,
        created_at: str,
        last_seen_at: str,
    ) -> None:
        """Insert or update instance."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO sandbox_instances (
                    instance_id, lease_id, provider_session_id, status,
                    created_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(instance_id) DO UPDATE SET
                    lease_id = excluded.lease_id,
                    provider_session_id = excluded.provider_session_id,
                    status = excluded.status,
                    last_seen_at = excluded.last_seen_at
                """,
                (instance_id, lease_id, provider_session_id, status, created_at, last_seen_at),
            )

    def update_instance_last_seen(self, instance_id: str, last_seen_at: str) -> None:
        """Update instance last_seen_at."""
        with self._transaction() as conn:
            conn.execute(
                "UPDATE sandbox_instances SET last_seen_at = ? WHERE instance_id = ?",
                (last_seen_at, instance_id),
            )

    # === TERMINAL OPERATIONS ===
    # (Implementations follow same pattern as lease operations)

    def upsert_terminal(
        self,
        terminal_id: str,
        thread_id: str,
        lease_id: str,
        cwd: str,
        env_delta_json: str,
        state_version: int,
        created_at: str,
        updated_at: str,
    ) -> None:
        """Insert or update terminal."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO abstract_terminals (
                    terminal_id, thread_id, lease_id, cwd, env_delta_json,
                    state_version, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(terminal_id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    lease_id = excluded.lease_id,
                    cwd = excluded.cwd,
                    env_delta_json = excluded.env_delta_json,
                    state_version = excluded.state_version,
                    updated_at = excluded.updated_at
                """,
                (terminal_id, thread_id, lease_id, cwd, env_delta_json, state_version, created_at, updated_at),
            )

    def update_terminal_state(
        self,
        terminal_id: str,
        cwd: str,
        env_delta_json: str,
        state_version: int,
        updated_at: str,
    ) -> None:
        """Update terminal state."""
        with self._transaction() as conn:
            conn.execute(
                """
                UPDATE abstract_terminals
                SET cwd = ?, env_delta_json = ?, state_version = ?, updated_at = ?
                WHERE terminal_id = ?
                """,
                (cwd, env_delta_json, state_version, updated_at, terminal_id),
            )

    def get_terminal(self, terminal_id: str) -> dict[str, Any] | None:
        """Get terminal by ID."""
        with self._transaction() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM abstract_terminals WHERE terminal_id = ?", (terminal_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_terminals_by_thread(self, thread_id: str) -> list[dict[str, Any]]:
        """List terminals for thread."""
        with self._transaction() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM abstract_terminals WHERE thread_id = ? ORDER BY created_at DESC",
                (thread_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_terminal(self, terminal_id: str) -> None:
        """Delete terminal and related commands."""
        with self._transaction() as conn:
            # Delete related commands first
            conn.execute("DELETE FROM terminal_commands WHERE terminal_id = ?", (terminal_id,))
            conn.execute("DELETE FROM abstract_terminals WHERE terminal_id = ?", (terminal_id,))

    # === TERMINAL POINTER OPERATIONS ===
    # === SESSION OPERATIONS ===
    # === EVENT OPERATIONS ===
    # (Remaining methods follow same pattern - omitted for brevity)

    def upsert_terminal_pointer(
        self,
        thread_id: str,
        active_terminal_id: str,
        default_terminal_id: str,
        updated_at: str,
    ) -> None:
        """Insert or update terminal pointer."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO thread_terminal_pointers (
                    thread_id, active_terminal_id, default_terminal_id, updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    active_terminal_id = excluded.active_terminal_id,
                    default_terminal_id = excluded.default_terminal_id,
                    updated_at = excluded.updated_at
                """,
                (thread_id, active_terminal_id, default_terminal_id, updated_at),
            )

    def get_terminal_pointer(self, thread_id: str) -> dict[str, Any] | None:
        """Get terminal pointer for thread."""
        with self._transaction() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM thread_terminal_pointers WHERE thread_id = ?", (thread_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_terminal_pointer_active(
        self, thread_id: str, active_terminal_id: str, updated_at: str
    ) -> None:
        """Update active terminal."""
        with self._transaction() as conn:
            conn.execute(
                """
                UPDATE thread_terminal_pointers
                SET active_terminal_id = ?, updated_at = ?
                WHERE thread_id = ?
                """,
                (active_terminal_id, updated_at, thread_id),
            )

    def delete_terminal_pointer(self, thread_id: str) -> None:
        """Delete terminal pointer."""
        with self._transaction() as conn:
            conn.execute(
                "DELETE FROM thread_terminal_pointers WHERE thread_id = ?", (thread_id,)
            )

    def upsert_session(
        self,
        chat_session_id: str,
        thread_id: str,
        terminal_id: str,
        lease_id: str,
        runtime_id: str | None,
        status: str,
        idle_ttl_sec: int,
        max_duration_sec: int,
        budget_json: str | None,
        started_at: str,
        last_active_at: str,
        ended_at: str | None,
        close_reason: str | None,
    ) -> None:
        """Insert or update session."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (
                    chat_session_id, thread_id, terminal_id, lease_id, runtime_id,
                    status, idle_ttl_sec, max_duration_sec, budget_json,
                    started_at, last_active_at, ended_at, close_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_session_id) DO UPDATE SET
                    status = excluded.status,
                    runtime_id = excluded.runtime_id,
                    last_active_at = excluded.last_active_at,
                    ended_at = excluded.ended_at,
                    close_reason = excluded.close_reason
                """,
                (
                    chat_session_id,
                    thread_id,
                    terminal_id,
                    lease_id,
                    runtime_id,
                    status,
                    idle_ttl_sec,
                    max_duration_sec,
                    budget_json,
                    started_at,
                    last_active_at,
                    ended_at,
                    close_reason,
                ),
            )

    def update_session_status(
        self, chat_session_id: str, status: str, updated_at: str
    ) -> None:
        """Update session status."""
        with self._transaction() as conn:
            conn.execute(
                "UPDATE chat_sessions SET status = ? WHERE chat_session_id = ?",
                (status, chat_session_id),
            )

    def update_session_activity(
        self, chat_session_id: str, last_active_at: str
    ) -> None:
        """Update session last_active_at."""
        with self._transaction() as conn:
            conn.execute(
                "UPDATE chat_sessions SET last_active_at = ? WHERE chat_session_id = ?",
                (last_active_at, chat_session_id),
            )

    def update_session_close(
        self, chat_session_id: str, status: str, ended_at: str, close_reason: str
    ) -> None:
        """Close session."""
        with self._transaction() as conn:
            conn.execute(
                """
                UPDATE chat_sessions
                SET status = ?, ended_at = ?, close_reason = ?
                WHERE chat_session_id = ?
                """,
                (status, ended_at, close_reason, chat_session_id),
            )

    def get_session(self, chat_session_id: str) -> dict[str, Any] | None:
        """Get session by ID."""
        with self._transaction() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM chat_sessions WHERE chat_session_id = ?", (chat_session_id,)
            ).fetchone()
            return dict(row) if row else None

    def insert_lease_event(
        self,
        event_id: str,
        lease_id: str,
        event_type: str,
        source: str,
        payload_json: str | None,
        error: str | None,
        created_at: str,
    ) -> None:
        """Insert lease event."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO lease_events (
                    event_id, lease_id, event_type, source, payload_json, error, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, lease_id, event_type, source, payload_json, error, created_at),
            )

    def insert_provider_event(
        self,
        provider_name: str,
        instance_id: str,
        event_type: str,
        payload_json: str | None,
        matched_lease_id: str | None,
        created_at: str,
    ) -> None:
        """Insert provider event."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO provider_events (
                    provider_name, instance_id, event_type, payload_json,
                    matched_lease_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (provider_name, instance_id, event_type, payload_json, matched_lease_id, created_at),
            )
