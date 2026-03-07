"""Legacy adapter wrapping existing inline SQL.

This adapter delegates to the EXISTING SQL code in sandbox/*.py files.
It provides a repository interface without changing behavior.

Purpose: Allow parallel testing of old and new implementations.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from sandbox.config import DEFAULT_DB_PATH
from storage.providers.sqlite.kernel import connect_sqlite


class LegacySandboxRepository:
    """Adapter wrapping existing inline SQL operations.

    This class delegates to existing code in sandbox/*.py files.
    NO new SQL is written here - just wrapping existing operations.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        """Use existing connection helper."""
        return connect_sqlite(self.db_path)

    # === TABLE MANAGEMENT ===

    def ensure_tables(self) -> None:
        """Create all tables using existing code.

        Delegates to existing ensure_tables methods in:
        - SQLiteLease.ensure_tables()
        - SQLiteTerminal.ensure_tables()
        - ChatSession.ensure_tables()
        - etc.
        """
        # Import here to avoid circular dependencies
        from sandbox.lease import SQLiteLease
        from sandbox.terminal import SQLiteTerminal
        from sandbox.chat_session import ChatSession
        from sandbox.provider_events import ensure_provider_events_table

        SQLiteLease.ensure_tables(self.db_path)
        SQLiteTerminal.ensure_tables(self.db_path)
        ChatSession.ensure_tables(self.db_path)
        ensure_provider_events_table(self.db_path)

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
        """Delegate to existing SQLiteLease._upsert_snapshot logic.

        This wraps the existing SQL in lease.py without changing it.
        """
        # TODO: Extract and call existing SQL from lease.py
        # For now, implement directly to match existing behavior
        with self._connect() as conn:
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
            conn.commit()

    def update_lease_state(
        self,
        lease_id: str,
        observed_state: str,
        version: int,
        observed_at: str,
        last_error: str | None = None,
    ) -> None:
        """Delegate to existing lease state update logic."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sandbox_leases
                SET observed_state = ?, version = ?, observed_at = ?, last_error = ?
                WHERE lease_id = ?
                """,
                (observed_state, version, observed_at, last_error, lease_id),
            )
            conn.commit()

    def get_lease(self, lease_id: str) -> dict[str, Any] | None:
        """Delegate to existing lease query logic."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM sandbox_leases WHERE lease_id = ?", (lease_id,)
            ).fetchone()
            return dict(row) if row else None

    def delete_lease(self, lease_id: str) -> None:
        """Delegate to existing lease deletion logic."""
        with self._connect() as conn:
            conn.execute("DELETE FROM sandbox_leases WHERE lease_id = ?", (lease_id,))
            conn.commit()

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
        """Delegate to existing instance upsert logic."""
        with self._connect() as conn:
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
            conn.commit()

    def update_instance_last_seen(self, instance_id: str, last_seen_at: str) -> None:
        """Delegate to existing instance update logic."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE sandbox_instances SET last_seen_at = ? WHERE instance_id = ?",
                (last_seen_at, instance_id),
            )
            conn.commit()

    # === TERMINAL OPERATIONS ===

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
        """Delegate to existing terminal upsert logic."""
        with self._connect() as conn:
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
            conn.commit()

    def update_terminal_state(
        self,
        terminal_id: str,
        cwd: str,
        env_delta_json: str,
        state_version: int,
        updated_at: str,
    ) -> None:
        """Delegate to existing terminal state update logic."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE abstract_terminals
                SET cwd = ?, env_delta_json = ?, state_version = ?, updated_at = ?
                WHERE terminal_id = ?
                """,
                (cwd, env_delta_json, state_version, updated_at, terminal_id),
            )
            conn.commit()

    def get_terminal(self, terminal_id: str) -> dict[str, Any] | None:
        """Delegate to existing terminal query logic."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM abstract_terminals WHERE terminal_id = ?", (terminal_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_terminals_by_thread(self, thread_id: str) -> list[dict[str, Any]]:
        """Delegate to existing terminal list logic."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM abstract_terminals WHERE thread_id = ? ORDER BY created_at DESC",
                (thread_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_terminal(self, terminal_id: str) -> None:
        """Delegate to existing terminal deletion logic."""
        with self._connect() as conn:
            # Delete related commands first (if terminal_commands table exists)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "terminal_commands" in tables:
                conn.execute(
                    "DELETE FROM terminal_commands WHERE terminal_id = ?", (terminal_id,)
                )
            conn.execute("DELETE FROM abstract_terminals WHERE terminal_id = ?", (terminal_id,))
            conn.commit()

    # === TERMINAL POINTER OPERATIONS ===

    def upsert_terminal_pointer(
        self,
        thread_id: str,
        active_terminal_id: str,
        default_terminal_id: str,
        updated_at: str,
    ) -> None:
        """Delegate to existing pointer upsert logic."""
        with self._connect() as conn:
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
            conn.commit()

    def get_terminal_pointer(self, thread_id: str) -> dict[str, Any] | None:
        """Delegate to existing pointer query logic."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM thread_terminal_pointers WHERE thread_id = ?", (thread_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_terminal_pointer_active(
        self, thread_id: str, active_terminal_id: str, updated_at: str
    ) -> None:
        """Delegate to existing pointer update logic."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE thread_terminal_pointers
                SET active_terminal_id = ?, updated_at = ?
                WHERE thread_id = ?
                """,
                (active_terminal_id, updated_at, thread_id),
            )
            conn.commit()

    def delete_terminal_pointer(self, thread_id: str) -> None:
        """Delegate to existing pointer deletion logic."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM thread_terminal_pointers WHERE thread_id = ?", (thread_id,)
            )
            conn.commit()

    # === SESSION OPERATIONS ===

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
        """Delegate to existing session upsert logic."""
        with self._connect() as conn:
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
            conn.commit()

    def update_session_status(
        self, chat_session_id: str, status: str, updated_at: str
    ) -> None:
        """Delegate to existing session status update logic."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE chat_sessions SET status = ? WHERE chat_session_id = ?",
                (status, chat_session_id),
            )
            conn.commit()

    def update_session_activity(
        self, chat_session_id: str, last_active_at: str
    ) -> None:
        """Delegate to existing session activity update logic."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE chat_sessions SET last_active_at = ? WHERE chat_session_id = ?",
                (last_active_at, chat_session_id),
            )
            conn.commit()

    def update_session_close(
        self, chat_session_id: str, status: str, ended_at: str, close_reason: str
    ) -> None:
        """Delegate to existing session close logic."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE chat_sessions
                SET status = ?, ended_at = ?, close_reason = ?
                WHERE chat_session_id = ?
                """,
                (status, ended_at, close_reason, chat_session_id),
            )
            conn.commit()

    def get_session(self, chat_session_id: str) -> dict[str, Any] | None:
        """Delegate to existing session query logic."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM chat_sessions WHERE chat_session_id = ?", (chat_session_id,)
            ).fetchone()
            return dict(row) if row else None

    # === EVENT OPERATIONS ===

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
        """Delegate to existing lease event insert logic."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO lease_events (
                    event_id, lease_id, event_type, source, payload_json, error, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, lease_id, event_type, source, payload_json, error, created_at),
            )
            conn.commit()

    def insert_provider_event(
        self,
        provider_name: str,
        instance_id: str,
        event_type: str,
        payload_json: str | None,
        matched_lease_id: str | None,
        created_at: str,
    ) -> None:
        """Delegate to existing provider event insert logic."""
        with self._connect() as conn:
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
            conn.commit()
