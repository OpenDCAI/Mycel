from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite, resolve_role_db_path

REQUIRED_ABSTRACT_TERMINAL_COLUMNS = {
    "terminal_id",
    "thread_id",
    "sandbox_runtime_id",
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
    cwd: str
    env_delta: dict[str, str] = field(default_factory=dict)
    state_version: int = 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "cwd": self.cwd,
                "env_delta": self.env_delta,
                "state_version": self.state_version,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> TerminalState:
        obj = json.loads(data)
        return cls(
            cwd=obj["cwd"],
            env_delta=obj.get("env_delta", {}),
            state_version=obj.get("state_version", 0),
        )


class AbstractTerminal(ABC):
    def __init__(
        self,
        terminal_id: str,
        thread_id: str,
        sandbox_runtime_id: str,
        state: TerminalState,
    ):
        self.terminal_id = terminal_id
        self.thread_id = thread_id
        self.sandbox_runtime_id = sandbox_runtime_id
        self._state = state

    def get_state(self) -> TerminalState:
        return self._state

    def update_state(self, state: TerminalState) -> None:
        state.state_version = self._state.state_version + 1
        self._state = state
        self._persist_state()

    @abstractmethod
    def _persist_state(self) -> None: ...


class SQLiteTerminal(AbstractTerminal):
    def __init__(
        self,
        terminal_id: str,
        thread_id: str,
        sandbox_runtime_id: str,
        state: TerminalState,
        db_path: Path | None = None,
    ):
        super().__init__(terminal_id, thread_id, sandbox_runtime_id, state)
        self.db_path = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)

    def _persist_state(self) -> None:
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


def terminal_from_row(row: dict, db_path: Path) -> AbstractTerminal:
    state = TerminalState(
        cwd=row.get("cwd", "/root"),
        env_delta=json.loads(row.get("env_delta_json", "{}")),
        state_version=int(row.get("state_version", 0)),
    )
    return SQLiteTerminal(
        terminal_id=row["terminal_id"],
        thread_id=row["thread_id"],
        sandbox_runtime_id=row["sandbox_runtime_id"],
        state=state,
        db_path=db_path,
    )
