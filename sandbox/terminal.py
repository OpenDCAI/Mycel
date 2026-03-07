"""AbstractTerminal - Durable terminal identity + state snapshot.

This module implements the terminal abstraction layer that separates
durable terminal state (cwd, env_delta) from ephemeral runtime processes.

Architecture:
    Thread → AbstractTerminal (durable state) → SandboxLease → Instance
    Thread → ChatSession → PhysicalTerminalRuntime (ephemeral process)
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from storage.providers.sqlite.kernel import connect_sqlite

from sandbox.config import DEFAULT_DB_PATH

if TYPE_CHECKING:
    from storage.providers.sqlite.sandbox_repository_protocol import SandboxRepositoryProtocol

REQUIRED_ABSTRACT_TERMINAL_COLUMNS = {
    "terminal_id",
    "thread_id",
    "lease_id",
    "cwd",
    "env_delta_json",
    "state_version",
    "created_at",
    "updated_at",
}

REQUIRED_TERMINAL_POINTER_COLUMNS = {
    "thread_id",
    "active_terminal_id",
    "default_terminal_id",
    "updated_at",
}


def _connect(db_path: Path) -> sqlite3.Connection:
    return connect_sqlite(db_path)


@dataclass
class TerminalState:
    """Terminal state snapshot.

    Represents the current state of a terminal that needs to persist
    across session boundaries. This is the "continuity" layer that
    makes terminals feel persistent even when physical processes die.
    """

    cwd: str
    env_delta: dict[str, str] = field(default_factory=dict)
    state_version: int = 0

    def to_json(self) -> str:
        """Serialize to JSON for DB storage."""
        return json.dumps(
            {
                "cwd": self.cwd,
                "env_delta": self.env_delta,
                "state_version": self.state_version,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> TerminalState:
        """Deserialize from JSON."""
        obj = json.loads(data)
        return cls(
            cwd=obj["cwd"],
            env_delta=obj.get("env_delta", {}),
            state_version=obj.get("state_version", 0),
        )


class AbstractTerminal(ABC):
    """Durable terminal identity + state snapshot.

    This is the logical terminal that persists across ChatSession boundaries.
    It does NOT own the physical process - that's owned by PhysicalTerminalRuntime.

    Responsibilities:
    - Store terminal identity (terminal_id, thread_id, lease_id)
    - Maintain state snapshot (cwd, env_delta, state_version)
    - Persist state to database
    - Provide state to PhysicalTerminalRuntime for hydration

    Does NOT:
    - Own physical shell/pty process
    - Execute commands directly
    - Manage process lifecycle
    """

    def __init__(
        self,
        terminal_id: str,
        thread_id: str,
        lease_id: str,
        state: TerminalState,
    ):
        self.terminal_id = terminal_id
        self.thread_id = thread_id
        self.lease_id = lease_id
        self._state = state

    def get_state(self) -> TerminalState:
        """Get current terminal state snapshot."""
        return self._state

    def update_state(self, state: TerminalState) -> None:
        """Update terminal state snapshot.

        This should be called after each command execution to persist
        the new cwd/env state.
        """
        state.state_version = self._state.state_version + 1
        self._state = state
        self._persist_state()

    @abstractmethod
    def _persist_state(self) -> None:
        """Persist state to storage backend."""
        ...


class SQLiteTerminal(AbstractTerminal):
    """SQLite-backed terminal implementation."""

    def __init__(
        self,
        terminal_id: str,
        thread_id: str,
        lease_id: str,
        state: TerminalState,
        db_path: Path = DEFAULT_DB_PATH,
    ):
        super().__init__(terminal_id, thread_id, lease_id, state)
        self.db_path = db_path

    def _persist_state(self) -> None:
        """Persist state to SQLite."""
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE abstract_terminals
                SET cwd = ?, env_delta_json = ?, state_version = ?, updated_at = ?
                WHERE terminal_id = ?
                """,
                (
                    self._state.cwd,
                    json.dumps(self._state.env_delta),
                    self._state.state_version,
                    datetime.now().isoformat(),
                    self.terminal_id,
                ),
            )
            conn.commit()


class TerminalStore:
    """Store for managing AbstractTerminal persistence.

    Handles CRUD operations for terminals in the database.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH, repository: SandboxRepositoryProtocol | None = None):
        self.db_path = db_path
        self._repo = repository  # @@@repository-migration - optional injection
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure terminal tables exist with multi-terminal schema."""
        with _connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
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
            conn.commit()
            abstract_cols = {row[1] for row in conn.execute("PRAGMA table_info(abstract_terminals)").fetchall()}
            pointer_cols = {row[1] for row in conn.execute("PRAGMA table_info(thread_terminal_pointers)").fetchall()}
            idx_rows = conn.execute("PRAGMA index_list(abstract_terminals)").fetchall()
            unique_index_names = [str(row[1]) for row in idx_rows if int(row[2]) == 1]
            unique_index_columns: dict[str, set[str]] = {}
            for idx_name in unique_index_names:
                info_rows = conn.execute(f"PRAGMA index_info({idx_name})").fetchall()
                unique_index_columns[idx_name] = {str(info_row[2]) for info_row in info_rows}

        missing_abstract = REQUIRED_ABSTRACT_TERMINAL_COLUMNS - abstract_cols
        if missing_abstract:
            raise RuntimeError(
                f"abstract_terminals schema mismatch: missing {sorted(missing_abstract)}. "
                "Purge ~/.leon/sandbox.db and retry."
            )

        missing_pointer = REQUIRED_TERMINAL_POINTER_COLUMNS - pointer_cols
        if missing_pointer:
            raise RuntimeError(
                f"thread_terminal_pointers schema mismatch: missing {sorted(missing_pointer)}. "
                "Purge ~/.leon/sandbox.db and retry."
            )

        # @@@no-thread-unique - Multi-terminal model requires thread_id to be non-unique in abstract_terminals.
        if any(cols == {"thread_id"} for cols in unique_index_columns.values()):
            raise RuntimeError(
                "abstract_terminals still has UNIQUE index from single-terminal schema. "
                "Purge ~/.leon/sandbox.db and retry."
            )

    def _row_to_terminal(self, row: sqlite3.Row) -> AbstractTerminal:
        state = TerminalState(
            cwd=row["cwd"],
            env_delta=json.loads(row["env_delta_json"]),
            state_version=row["state_version"],
        )
        return SQLiteTerminal(
            terminal_id=row["terminal_id"],
            thread_id=row["thread_id"],
            lease_id=row["lease_id"],
            state=state,
            db_path=self.db_path,
        )

    def _get_pointer_row(self, thread_id: str) -> sqlite3.Row | None:
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                """
                SELECT thread_id, active_terminal_id, default_terminal_id
                FROM thread_terminal_pointers
                WHERE thread_id = ?
                """,
                (thread_id,),
            ).fetchone()

    def _ensure_thread_pointer(self, thread_id: str, terminal_id: str) -> None:
        now = datetime.now().isoformat()
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT thread_id FROM thread_terminal_pointers WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            if row:
                return
            conn.execute(
                """
                INSERT INTO thread_terminal_pointers (thread_id, active_terminal_id, default_terminal_id, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (thread_id, terminal_id, terminal_id, now),
            )
            conn.commit()

    def get(self, thread_id: str) -> AbstractTerminal | None:
        """Get active terminal by thread_id."""
        return self.get_active(thread_id)

    def get_active(self, thread_id: str) -> AbstractTerminal | None:
        pointer = self._get_pointer_row(thread_id)
        if pointer is None:
            return None
        return self.get_by_id(str(pointer["active_terminal_id"]))

    def get_default(self, thread_id: str) -> AbstractTerminal | None:
        pointer = self._get_pointer_row(thread_id)
        if pointer is None:
            return None
        return self.get_by_id(str(pointer["default_terminal_id"]))

    def list_by_thread(self, thread_id: str) -> list[AbstractTerminal]:
        # @@@repository-migration - use repository if available
        if self._repo:
            rows = self._repo.list_terminals_by_thread(thread_id)
            return [self._row_to_terminal(row) for row in rows]  # type: ignore

        # Fallback to inline SQL
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT terminal_id, thread_id, lease_id, cwd, env_delta_json, state_version
                FROM abstract_terminals
                WHERE thread_id = ?
                ORDER BY created_at DESC
                """,
                (thread_id,),
            ).fetchall()
        return [self._row_to_terminal(row) for row in rows]

    def get_by_id(self, terminal_id: str) -> AbstractTerminal | None:
        """Get terminal by terminal_id."""
        # @@@repository-migration - use repository if available
        if self._repo:
            row = self._repo.get_terminal(terminal_id)
            if not row:
                return None
            return self._row_to_terminal(row)  # type: ignore - dict works like Row

        # Fallback to inline SQL
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT terminal_id, thread_id, lease_id, cwd, env_delta_json, state_version
                FROM abstract_terminals
                WHERE terminal_id = ?
                """,
                (terminal_id,),
            ).fetchone()

            if not row:
                return None

            return self._row_to_terminal(row)

    def set_active(self, thread_id: str, terminal_id: str) -> None:
        now = datetime.now().isoformat()
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT terminal_id, thread_id
                FROM abstract_terminals
                WHERE terminal_id = ?
                """,
                (terminal_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Terminal {terminal_id} not found")
            if row["thread_id"] != thread_id:
                raise RuntimeError(
                    f"Terminal {terminal_id} belongs to thread {row['thread_id']}, not thread {thread_id}"
                )
            pointer = conn.execute(
                "SELECT default_terminal_id FROM thread_terminal_pointers WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            if pointer is None:
                conn.execute(
                    """
                    INSERT INTO thread_terminal_pointers (thread_id, active_terminal_id, default_terminal_id, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (thread_id, terminal_id, terminal_id, now),
                )
            else:
                conn.execute(
                    """
                    UPDATE thread_terminal_pointers
                    SET active_terminal_id = ?, updated_at = ?
                    WHERE thread_id = ?
                    """,
                    (terminal_id, now, thread_id),
                )
            conn.commit()

    def create(
        self,
        terminal_id: str,
        thread_id: str,
        lease_id: str,
        initial_cwd: str = "/root",
    ) -> AbstractTerminal:
        """Create new terminal."""
        state = TerminalState(cwd=initial_cwd, env_delta={}, state_version=0)
        now = datetime.now().isoformat()

        with _connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO abstract_terminals (terminal_id, thread_id, lease_id, cwd, env_delta_json, state_version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    terminal_id,
                    thread_id,
                    lease_id,
                    state.cwd,
                    json.dumps(state.env_delta),
                    state.state_version,
                    now,
                    now,
                ),
            )
            conn.commit()

        self._ensure_thread_pointer(thread_id, terminal_id)
        return SQLiteTerminal(
            terminal_id=terminal_id,
            thread_id=thread_id,
            lease_id=lease_id,
            state=state,
            db_path=self.db_path,
        )

    def delete(self, terminal_id: str) -> None:
        """Delete terminal."""
        # @@@repository-migration - use repository if available
        if self._repo:
            terminal = self._repo.get_terminal(terminal_id)
            if terminal is None:
                return
            thread_id = str(terminal["thread_id"])

            self._repo.delete_terminal(terminal_id)

            pointer = self._repo.get_terminal_pointer(thread_id)
            if pointer:
                remaining = self._repo.list_terminals_by_thread(thread_id)
                if not remaining:
                    self._repo.delete_terminal_pointer(thread_id)
                else:
                    next_terminal_id = remaining[0]["terminal_id"]
                    active_id = pointer["active_terminal_id"]
                    default_id = pointer["default_terminal_id"]
                    new_active = next_terminal_id if active_id == terminal_id else active_id
                    new_default = next_terminal_id if default_id == terminal_id else default_id
                    self._repo.upsert_terminal_pointer(
                        thread_id, new_active, new_default, datetime.now().isoformat()
                    )
            return

        # Fallback to inline SQL
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            terminal = conn.execute(
                """
                SELECT terminal_id, thread_id
                FROM abstract_terminals
                WHERE terminal_id = ?
                """,
                (terminal_id,),
            ).fetchone()
            if terminal is None:
                return
            thread_id = str(terminal["thread_id"])

            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "terminal_commands" in tables:
                if "terminal_command_chunks" in tables:
                    conn.execute(
                        """
                        DELETE FROM terminal_command_chunks
                        WHERE command_id IN (
                            SELECT command_id FROM terminal_commands WHERE terminal_id = ?
                        )
                        """,
                        (terminal_id,),
                    )
                conn.execute(
                    "DELETE FROM terminal_commands WHERE terminal_id = ?",
                    (terminal_id,),
                )
            conn.execute(
                "DELETE FROM abstract_terminals WHERE terminal_id = ?",
                (terminal_id,),
            )

            pointer = conn.execute(
                """
                SELECT active_terminal_id, default_terminal_id
                FROM thread_terminal_pointers
                WHERE thread_id = ?
                """,
                (thread_id,),
            ).fetchone()
            if pointer:
                remaining = conn.execute(
                    """
                    SELECT terminal_id
                    FROM abstract_terminals
                    WHERE thread_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (thread_id,),
                ).fetchone()
                if remaining is None:
                    conn.execute(
                        "DELETE FROM thread_terminal_pointers WHERE thread_id = ?",
                        (thread_id,),
                    )
                else:
                    next_terminal_id = str(remaining["terminal_id"])
                    active_terminal_id = str(pointer["active_terminal_id"])
                    default_terminal_id = str(pointer["default_terminal_id"])
                    conn.execute(
                        """
                        UPDATE thread_terminal_pointers
                        SET active_terminal_id = ?, default_terminal_id = ?, updated_at = ?
                        WHERE thread_id = ?
                        """,
                        (
                            next_terminal_id if active_terminal_id == terminal_id else active_terminal_id,
                            next_terminal_id if default_terminal_id == terminal_id else default_terminal_id,
                            datetime.now().isoformat(),
                            thread_id,
                        ),
                    )
            conn.commit()

    def list_all(self) -> list[dict]:
        """List all terminals."""
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT terminal_id, thread_id, lease_id, cwd, state_version, created_at, updated_at
                FROM abstract_terminals
                ORDER BY created_at DESC
                """
            ).fetchall()

            return [dict(row) for row in rows]
