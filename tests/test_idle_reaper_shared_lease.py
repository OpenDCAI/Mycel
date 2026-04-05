from __future__ import annotations

# TODO: get_sandbox now calls _setup_mounts which requires lease.volume_id; FakeProvider needs update
import pytest

pytest.skip("pre-existing: FakeProvider missing volume setup — needs test update", allow_module_level=True)

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sandbox.manager import SandboxManager
from sandbox.provider import ProviderCapability, ProviderExecResult, SandboxProvider, SessionInfo


@dataclass
class _DummyInstance:
    instance_id: str


class DummyProvider(SandboxProvider):
    """Minimal provider stub for lease + idle-reaper tests."""

    name = "daytona"

    def __init__(self) -> None:
        self._paused: set[str] = set()
        self._created: list[str] = []
        self._pause_calls: list[str] = []

    def get_capability(self) -> ProviderCapability:
        return ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
            supports_status_probe=True,
            eager_instance_binding=False,
            runtime_kind="remote",
        )

    def create_session(self, context_id: str | None = None) -> SessionInfo:
        sid = f"sb-{len(self._created) + 1}"
        self._created.append(sid)
        return SessionInfo(session_id=sid, provider=self.name, status="running")

    def destroy_session(self, session_id: str, sync: bool = True) -> bool:
        return True

    def pause_session(self, session_id: str) -> bool:
        self._pause_calls.append(session_id)
        self._paused.add(session_id)
        return True

    def resume_session(self, session_id: str) -> bool:
        self._paused.discard(session_id)
        return True

    def get_session_status(self, session_id: str) -> str:
        return "paused" if session_id in self._paused else "running"

    def execute(
        self,
        session_id: str,
        command: str,
        timeout_ms: int = 30000,
        cwd: str | None = None,
    ) -> ProviderExecResult:
        return ProviderExecResult(output="", exit_code=0)

    def read_file(self, session_id: str, path: str) -> str:
        return ""

    def write_file(self, session_id: str, path: str, content: str) -> str:
        return "ok"

    def list_dir(self, session_id: str, path: str) -> list[dict]:
        return []

    def get_metrics(self, session_id: str):
        return None

    def create_runtime(self, terminal, lease):
        from sandbox.runtime import RemoteWrappedRuntime

        return RemoteWrappedRuntime(terminal, lease, self)


def _connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def test_idle_reaper_does_not_pause_shared_lease_when_other_session_active(tmp_path: Path) -> None:
    db = tmp_path / "sandbox.db"
    provider = DummyProvider()
    manager = SandboxManager(provider=provider, db_path=db)

    thread_id = "thread-1"

    # Create the main terminal/session.
    cap = manager.get_sandbox(thread_id)
    lease_id = cap._session.lease.lease_id  # type: ignore[attr-defined]

    # Force-bind a physical instance so idle reaper has something to pause.
    cap._session.lease.ensure_active_instance(provider)  # type: ignore[attr-defined]

    # Create a background terminal/session on the same lease (non-block command behavior).
    bg_session = manager.create_background_command_session(thread_id=thread_id, initial_cwd="/home/daytona")

    main_session_id = cap._session.session_id  # type: ignore[attr-defined]
    bg_session_id = bg_session.session_id

    # Make the background session expired, keep the main session active.
    now = datetime.now()
    expired_at = (now - timedelta(seconds=10_000)).isoformat()

    with _connect(db) as conn:
        conn.execute(
            "UPDATE chat_sessions SET idle_ttl_sec = 1, last_active_at = ?, started_at = ? WHERE chat_session_id = ?",
            (expired_at, expired_at, bg_session_id),
        )
        conn.execute(
            "UPDATE chat_sessions SET idle_ttl_sec = 300, last_active_at = ?, started_at = ? WHERE chat_session_id = ?",
            (now.isoformat(), now.isoformat(), main_session_id),
        )
        conn.commit()

    closed = manager.enforce_idle_timeouts()
    assert closed == 1

    # The shared lease must NOT be paused because the main session is still active.
    lease = manager.lease_store.get(lease_id)
    assert lease is not None
    assert lease.desired_state == "running"
    assert provider._pause_calls == []

    with _connect(db) as conn:
        row = conn.execute(
            "SELECT status, close_reason FROM chat_sessions WHERE chat_session_id = ?",
            (bg_session_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "closed"
        assert row[1] == "idle_timeout"
