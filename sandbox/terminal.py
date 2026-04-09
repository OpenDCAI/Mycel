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

from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite, resolve_role_db_path
from storage.runtime import build_terminal_repo, uses_supabase_storage

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


def _use_strategy_terminal(db_path: Path) -> bool:
    return uses_supabase_storage() and db_path == resolve_role_db_path(SQLiteDBRole.SANDBOX)


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
        db_path: Path | None = None,
    ):
        super().__init__(terminal_id, thread_id, lease_id, state)
        self.db_path = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)

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


class RepoBackedTerminal(AbstractTerminal):
    """Terminal implementation whose state writes go through TerminalRepo."""

    def __init__(self, terminal_id: str, thread_id: str, lease_id: str, state: TerminalState, *, repo):
        super().__init__(terminal_id, thread_id, lease_id, state)
        self._repo = repo

    def _persist_state(self) -> None:
        self._repo.persist_state(
            terminal_id=self.terminal_id,
            cwd=self._state.cwd,
            env_delta_json=json.dumps(self._state.env_delta),
            state_version=self._state.state_version,
        )


def terminal_from_row(row: dict, db_path: Path) -> AbstractTerminal:
    """Construct a terminal domain object from a repo dict."""
    state = TerminalState(
        cwd=row.get("cwd", "/root"),
        env_delta=json.loads(row.get("env_delta_json", "{}")),
        state_version=int(row.get("state_version", 0)),
    )
    if _use_strategy_terminal(db_path):
        # @@@strategy-terminal-write-owner - strategy-backed control-plane rows must
        # round-trip terminal state through TerminalRepo, not local sqlite side writes.
        return RepoBackedTerminal(
            terminal_id=row["terminal_id"],
            thread_id=row["thread_id"],
            lease_id=row["lease_id"],
            state=state,
            repo=build_terminal_repo(),
        )
    return SQLiteTerminal(
        terminal_id=row["terminal_id"],
        thread_id=row["thread_id"],
        lease_id=row["lease_id"],
        state=state,
        db_path=db_path,
    )
