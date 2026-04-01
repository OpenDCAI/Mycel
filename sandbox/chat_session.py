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

from sandbox.lifecycle import (
    ChatSessionState,
    assert_chat_session_transition,
    parse_chat_session_state,
)
from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite, resolve_role_db_path

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
        db_path: Path | None = None,
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
        self._db_path = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)

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
        db_path: Path | None = None,
        default_policy: ChatSessionPolicy | None = None,
        chat_session_repo=None,
    ):
        self.provider = provider
        self.db_path = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
        self.default_policy = default_policy or ChatSessionPolicy()
        self._live_sessions: dict[str, ChatSession] = {}
        if chat_session_repo:
            self._repo = chat_session_repo
        else:
            from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo

            self._repo = SQLiteChatSessionRepo(db_path=db_path)

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

    def _build_runtime(self, terminal: AbstractTerminal, lease: SandboxLease) -> PhysicalTerminalRuntime:
        return self.provider.create_runtime(terminal, lease)

    def get(self, thread_id: str, terminal_id: str | None = None) -> ChatSession | None:
        if terminal_id is None:
            from sandbox.terminal import terminal_from_row
            from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo

            # @@@thread-get-back-compat - Legacy callers query by thread only; route to current active terminal.
            _term_repo = SQLiteTerminalRepo(db_path=self.db_path)
            try:
                _term_row = _term_repo.get_active(thread_id)
            finally:
                _term_repo.close()
            if _term_row is None:
                return None
            terminal_id = _term_row["terminal_id"]
        live = self._live_sessions.get(terminal_id)
        if live:
            if live.is_expired():
                self.delete(live.session_id, reason="expired")
                return None
            return live

        row = self._repo.get_session(thread_id, terminal_id)

        if not row:
            return None

        from sandbox.lease import lease_from_row
        from sandbox.terminal import terminal_from_row
        from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo
        from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo

        _term_repo = SQLiteTerminalRepo(db_path=self.db_path)
        try:
            _term_row = _term_repo.get_by_id(row["terminal_id"])
        finally:
            _term_repo.close()
        terminal = terminal_from_row(_term_row, self.db_path) if _term_row else None
        _lease_repo = SQLiteLeaseRepo(db_path=self.db_path)
        try:
            _lease_row = _lease_repo.get(row["lease_id"])
        finally:
            _lease_repo.close()
        lease = lease_from_row(_lease_row, self.db_path) if _lease_row else None
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

        self._repo.create_session(
            session_id=session_id,
            thread_id=thread_id,
            terminal_id=terminal.terminal_id,
            lease_id=lease.lease_id,
            runtime_id=runtime_id,
            status="active",
            idle_ttl_sec=policy.idle_ttl_sec,
            max_duration_sec=policy.max_duration_sec,
            started_at=now.isoformat(),
            last_active_at=now.isoformat(),
        )

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
        current_raw = self._repo.load_status(session_id)
        if not current_raw:
            return
        current = parse_chat_session_state(current_raw)
        target = ChatSessionState.PAUSED if current == ChatSessionState.PAUSED else ChatSessionState.ACTIVE
        assert_chat_session_transition(current, target, reason="touch_manager")
        now = datetime.now().isoformat()
        self._repo.touch(session_id, last_active_at=now, status=target.value)
        for session in self._live_sessions.values():
            if session.session_id == session_id:
                session.last_active_at = datetime.fromisoformat(now)
                session.status = target.value
                break

    def pause(self, session_id: str) -> None:
        self._repo.pause(session_id)
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
        self._repo.resume(session_id)
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

        self._repo.delete_session(session_id, reason=reason)

    def close(self, reason: str = "manager_close") -> None:
        for live_terminal_id, session in list(self._live_sessions.items()):
            assert_chat_session_transition(
                parse_chat_session_state(session.status),
                ChatSessionState.CLOSED,
                reason=reason,
            )
            self._close_runtime(session, reason=reason)
            self._live_sessions.pop(live_terminal_id, None)

        self._repo.close_all_active(reason)
        self._repo.close()

    def list_active(self) -> list[dict]:
        return self._repo.list_active()

    def list_all(self) -> list[dict]:
        return self._repo.list_all()

    def cleanup_expired(self) -> int:
        count = 0
        for session in self._repo.list_active():
            started_at = datetime.fromisoformat(session["started_at"])
            last_active_at = datetime.fromisoformat(session["last_active_at"])
            idle_ttl_sec = self.default_policy.idle_ttl_sec
            max_duration_sec = self.default_policy.max_duration_sec
            policy = self._repo.get_session_policy(session["session_id"])
            if policy:
                idle_ttl_sec = policy["idle_ttl_sec"]
                max_duration_sec = policy["max_duration_sec"]
            now = datetime.now()
            idle_elapsed = (now - last_active_at).total_seconds()
            total_elapsed = (now - started_at).total_seconds()
            if idle_elapsed > idle_ttl_sec or total_elapsed > max_duration_sec:
                self.delete(session["session_id"], reason="expired")
                count += 1
        return count
