"""ChatSession - lifecycle/policy envelope for PhysicalTerminalRuntime.

Architecture:
    Thread (durable) -> ChatSession (policy window) -> PhysicalTerminalRuntime (ephemeral)
                     -> AbstractTerminal (reference)
                     -> SandboxLease (reference)
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from storage.providers.sqlite.kernel import connect_sqlite

from sandbox.config import DEFAULT_DB_PATH
from sandbox.lifecycle import (
    ChatSessionState,
    assert_chat_session_transition,
    parse_chat_session_state,
)

if TYPE_CHECKING:
    from sandbox.lease import SandboxLease
    from sandbox.provider import SandboxProvider
    from sandbox.runtime import PhysicalTerminalRuntime
    from sandbox.terminal import AbstractTerminal

REQUIRED_CHAT_SESSION_COLUMNS = {
    "chat_session_id",
    "thread_id",
    "terminal_id",
    "lease_id",
    "runtime_id",
    "status",
    "idle_ttl_sec",
    "max_duration_sec",
    "budget_json",
    "started_at",
    "last_active_at",
    "ended_at",
    "close_reason",
}


def _connect(db_path: Path) -> sqlite3.Connection:
    return connect_sqlite(db_path)


@dataclass
class ChatSessionPolicy:
    """Policy configuration for ChatSession lifecycle."""

    idle_ttl_sec: int = 600
    max_duration_sec: int = 86400


class ChatSession:
    """Policy/lifecycle window for PhysicalTerminalRuntime."""

    def __init__(
        self,
        session_id: str,
        thread_id: str,
        terminal: AbstractTerminal,
        lease: SandboxLease,
        runtime: PhysicalTerminalRuntime,
        policy: ChatSessionPolicy,
        started_at: datetime,
        last_active_at: datetime,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        runtime_id: str | None = None,
        status: str = "active",
        budget_json: str | None = None,
        ended_at: datetime | None = None,
        close_reason: str | None = None,
    ):
        self.session_id = session_id
        self.thread_id = thread_id
        self.terminal = terminal
        self.lease = lease
        self.runtime = runtime
        self.policy = policy
        self.started_at = started_at
        self.last_active_at = last_active_at
        self.runtime_id = runtime_id
        parse_chat_session_state(status)
        self.status = status
        self.budget_json = budget_json
        self.ended_at = ended_at
        self.close_reason = close_reason
        self._db_path = db_path

    def is_expired(self) -> bool:
        now = datetime.now()
        idle_seconds = (now - self.last_active_at).total_seconds()
        total_seconds = (now - self.started_at).total_seconds()
        return idle_seconds > self.policy.idle_ttl_sec or total_seconds > self.policy.max_duration_sec

    def touch(self) -> None:
        now = datetime.now()
        self.last_active_at = now
        if self.status != "paused":
            assert_chat_session_transition(
                parse_chat_session_state(self.status),
                ChatSessionState.ACTIVE,
                reason="touch",
            )
            self.status = "active"
        with _connect(self._db_path) as conn:
            conn.execute(
                """
                UPDATE chat_sessions
                SET last_active_at = ?, status = ?
                WHERE chat_session_id = ?
                """,
                (now.isoformat(), self.status, self.session_id),
            )
            conn.commit()

    async def close(self, reason: str = "closed") -> None:
        await self.runtime.close()
        assert_chat_session_transition(
            parse_chat_session_state(self.status),
            ChatSessionState.CLOSED,
            reason=reason,
        )
        self.status = "closed"
        self.ended_at = datetime.now()
        self.close_reason = reason
        with _connect(self._db_path) as conn:
            conn.execute(
                """
                UPDATE chat_sessions
                SET status = ?, ended_at = ?, close_reason = ?
                WHERE chat_session_id = ?
                """,
                (
                    self.status,
                    self.ended_at.isoformat(),
                    self.close_reason,
                    self.session_id,
                ),
            )
            conn.commit()


class ChatSessionManager:
    """Manager for ChatSession lifecycle."""

    def __init__(
        self,
        provider: SandboxProvider,
        db_path: Path = DEFAULT_DB_PATH,
        default_policy: ChatSessionPolicy | None = None,
    ):
        self.provider = provider
        self.db_path = db_path
        self.default_policy = default_policy or ChatSessionPolicy()
        self._live_sessions: dict[str, ChatSession] = {}
        self._ensure_tables()

    def _close_runtime(self, session: ChatSession, reason: str) -> None:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is None:
            asyncio.run(session.close(reason=reason))
            return

        error: list[Exception] = []

        def _runner():
            try:
                asyncio.run(session.close(reason=reason))
            except Exception as exc:  # pragma: no cover - defensive relay
                error.append(exc)

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()
        if error:
            raise error[0]

    def _ensure_tables(self) -> None:
        with _connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
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
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_thread_status
                ON chat_sessions(thread_id, status, started_at DESC)
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
                CREATE INDEX IF NOT EXISTS idx_terminal_commands_terminal_created
                ON terminal_commands(terminal_id, created_at DESC)
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
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_sessions_active_thread
                ON chat_sessions(terminal_id)
                WHERE status IN ('active', 'idle', 'paused')
                """
            )
            conn.commit()
            cols = {row[1] for row in conn.execute("PRAGMA table_info(chat_sessions)").fetchall()}
            idx_rows = conn.execute("PRAGMA index_list(chat_sessions)").fetchall()
            unique_indexes = [str(row[1]) for row in idx_rows if int(row[2]) == 1]
            unique_index_columns: dict[str, set[str]] = {}
            for idx_name in unique_indexes:
                info_rows = conn.execute(f"PRAGMA index_info({idx_name})").fetchall()
                unique_index_columns[idx_name] = {str(info_row[2]) for info_row in info_rows}
        missing = REQUIRED_CHAT_SESSION_COLUMNS - cols
        if missing:
            raise RuntimeError(
                f"chat_sessions schema mismatch: missing {sorted(missing)}. Purge ~/.leon/sandbox.db and retry."
            )
        # @@@single-active-per-terminal - multi-terminal model allows many active sessions per thread, one per terminal.
        if any(cols == {"thread_id"} for cols in unique_index_columns.values()):
            raise RuntimeError(
                "chat_sessions still has UNIQUE index on thread_id from old schema. Purge ~/.leon/sandbox.db and retry."
            )

    def _build_runtime(self, terminal: AbstractTerminal, lease: SandboxLease) -> PhysicalTerminalRuntime:
        return self.provider.create_runtime(terminal, lease)

    def _load_status(self, session_id: str) -> str | None:
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT status
                FROM chat_sessions
                WHERE chat_session_id = ?
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return str(row[0]) if row else None

    def get(self, thread_id: str, terminal_id: str | None = None) -> ChatSession | None:
        if terminal_id is None:
            from sandbox.terminal import TerminalStore

            # @@@thread-get-back-compat - Legacy callers query by thread only; route to current active terminal.
            terminal = TerminalStore(db_path=self.db_path).get_active(thread_id)
            if terminal is None:
                return None
            terminal_id = terminal.terminal_id
        live = self._live_sessions.get(terminal_id)
        if live:
            if live.is_expired():
                self.delete(live.session_id, reason="expired")
                return None
            return live

        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT chat_session_id AS session_id, thread_id, terminal_id, lease_id,
                       runtime_id, status, idle_ttl_sec, max_duration_sec,
                       budget_json, started_at, last_active_at, ended_at, close_reason
                FROM chat_sessions
                WHERE thread_id = ? AND terminal_id = ? AND status IN ('active', 'idle', 'paused')
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (thread_id, terminal_id),
            ).fetchone()

        if not row:
            return None

        from sandbox.lease import LeaseStore
        from sandbox.terminal import TerminalStore

        terminal = TerminalStore(db_path=self.db_path).get_by_id(row["terminal_id"])
        lease = LeaseStore(db_path=self.db_path).get(row["lease_id"])
        if not terminal or not lease:
            return None

        session = ChatSession(
            session_id=row["session_id"],
            thread_id=row["thread_id"],
            terminal=terminal,
            lease=lease,
            runtime=self._build_runtime(terminal, lease),
            policy=ChatSessionPolicy(
                idle_ttl_sec=row["idle_ttl_sec"],
                max_duration_sec=row["max_duration_sec"],
            ),
            started_at=datetime.fromisoformat(row["started_at"]),
            last_active_at=datetime.fromisoformat(row["last_active_at"]),
            db_path=self.db_path,
            runtime_id=row["runtime_id"],
            status=row["status"],
            budget_json=row["budget_json"],
            ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            close_reason=row["close_reason"],
        )
        session.runtime.bind_session(session.session_id)
        if session.is_expired():
            self.delete(session.session_id, reason="expired")
            return None
        self._live_sessions[terminal_id] = session
        return session

    def create(
        self,
        session_id: str,
        thread_id: str,
        terminal: AbstractTerminal,
        lease: SandboxLease,
        policy: ChatSessionPolicy | None = None,
    ) -> ChatSession:
        policy = policy or self.default_policy
        now = datetime.now()

        existing = self._live_sessions.get(terminal.terminal_id)
        if existing and existing.session_id != session_id:
            self._close_runtime(existing, reason="superseded")
            self._live_sessions.pop(terminal.terminal_id, None)

        runtime = self._build_runtime(terminal, lease)
        runtime_id = getattr(runtime, "runtime_id", None)

        with _connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE chat_sessions
                SET status = 'closed', ended_at = ?, close_reason = 'superseded'
                WHERE terminal_id = ? AND status IN ('active', 'idle', 'paused')
                """,
                (now.isoformat(), terminal.terminal_id),
            )
            conn.execute(
                """
                INSERT INTO chat_sessions (
                    chat_session_id, thread_id, terminal_id, lease_id,
                    runtime_id, status, idle_ttl_sec, max_duration_sec,
                    budget_json, started_at, last_active_at, ended_at, close_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    thread_id,
                    terminal.terminal_id,
                    lease.lease_id,
                    runtime_id,
                    "active",
                    policy.idle_ttl_sec,
                    policy.max_duration_sec,
                    None,
                    now.isoformat(),
                    now.isoformat(),
                    None,
                    None,
                ),
            )
            conn.commit()

        session = ChatSession(
            session_id=session_id,
            thread_id=thread_id,
            terminal=terminal,
            lease=lease,
            runtime=runtime,
            policy=policy,
            started_at=now,
            last_active_at=now,
            db_path=self.db_path,
            runtime_id=runtime_id,
            status="active",
        )
        session.runtime.bind_session(session.session_id)
        self._live_sessions[terminal.terminal_id] = session
        return session

    def touch(self, session_id: str) -> None:
        current_raw = self._load_status(session_id)
        if not current_raw:
            return
        current = parse_chat_session_state(current_raw)
        target = ChatSessionState.PAUSED if current == ChatSessionState.PAUSED else ChatSessionState.ACTIVE
        assert_chat_session_transition(current, target, reason="touch_manager")
        now = datetime.now().isoformat()
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE chat_sessions
                SET last_active_at = ?, status = ?
                WHERE chat_session_id = ?
                """,
                (now, target.value, session_id),
            )
            conn.commit()
        for session in self._live_sessions.values():
            if session.session_id == session_id:
                session.last_active_at = datetime.fromisoformat(now)
                session.status = target.value
                break

    def pause(self, session_id: str) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE chat_sessions
                SET status = 'paused', close_reason = 'paused'
                WHERE chat_session_id = ? AND status IN ('active', 'idle')
                """,
                (session_id,),
            )
            conn.commit()
        for session in self._live_sessions.values():
            if session.session_id == session_id:
                assert_chat_session_transition(
                    parse_chat_session_state(session.status),
                    ChatSessionState.PAUSED,
                    reason="pause",
                )
                session.status = "paused"
                session.close_reason = "paused"
                break

    def resume(self, session_id: str) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE chat_sessions
                SET status = 'active', close_reason = NULL
                WHERE chat_session_id = ? AND status = 'paused'
                """,
                (session_id,),
            )
            conn.commit()
        for session in self._live_sessions.values():
            if session.session_id == session_id:
                assert_chat_session_transition(
                    parse_chat_session_state(session.status),
                    ChatSessionState.ACTIVE,
                    reason="resume",
                )
                session.status = "active"
                session.close_reason = None
                break

    def delete(self, session_id: str, *, reason: str = "closed") -> None:
        session_to_close = None
        for live_terminal_id, session in list(self._live_sessions.items()):
            if session.session_id == session_id:
                session_to_close = session
                del self._live_sessions[live_terminal_id]
                break

        if session_to_close:
            assert_chat_session_transition(
                parse_chat_session_state(session_to_close.status),
                ChatSessionState.CLOSED,
                reason=reason,
            )
            self._close_runtime(session_to_close, reason=reason)
            return

        with _connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE chat_sessions
                SET status = 'closed', ended_at = ?, close_reason = ?
                WHERE chat_session_id = ? AND status IN ('active', 'idle', 'paused')
                """,
                (datetime.now().isoformat(), reason, session_id),
            )
            conn.commit()

    def close(self, reason: str = "manager_close") -> None:
        for live_terminal_id, session in list(self._live_sessions.items()):
            assert_chat_session_transition(
                parse_chat_session_state(session.status),
                ChatSessionState.CLOSED,
                reason=reason,
            )
            self._close_runtime(session, reason=reason)
            self._live_sessions.pop(live_terminal_id, None)

        with _connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE chat_sessions
                SET status = 'closed', ended_at = ?, close_reason = ?
                WHERE status IN ('active', 'idle', 'paused')
                """,
                (datetime.now().isoformat(), reason),
            )
            conn.commit()

    def list_active(self) -> list[dict]:
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT chat_session_id AS session_id, thread_id, terminal_id, lease_id,
                       runtime_id, status, idle_ttl_sec, max_duration_sec,
                       budget_json, started_at, last_active_at,
                       ended_at, close_reason
                FROM chat_sessions
                WHERE status IN ('active', 'idle', 'paused')
                ORDER BY started_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def list_all(self) -> list[dict]:
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT chat_session_id AS session_id, thread_id, terminal_id, lease_id,
                       runtime_id, status, budget_json, started_at, last_active_at,
                       ended_at, close_reason
                FROM chat_sessions
                ORDER BY started_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def cleanup_expired(self) -> int:
        count = 0
        for session in self.list_active():
            started_at = datetime.fromisoformat(session["started_at"])
            last_active_at = datetime.fromisoformat(session["last_active_at"])
            idle_ttl_sec = self.default_policy.idle_ttl_sec
            max_duration_sec = self.default_policy.max_duration_sec
            with _connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT idle_ttl_sec, max_duration_sec
                    FROM chat_sessions
                    WHERE chat_session_id = ?
                    """,
                    (session["session_id"],),
                ).fetchone()
            if row:
                idle_ttl_sec = row["idle_ttl_sec"]
                max_duration_sec = row["max_duration_sec"]
            now = datetime.now()
            idle_elapsed = (now - last_active_at).total_seconds()
            total_elapsed = (now - started_at).total_seconds()
            if idle_elapsed > idle_ttl_sec or total_elapsed > max_duration_sec:
                self.delete(session["session_id"], reason="expired")
                count += 1
        return count
