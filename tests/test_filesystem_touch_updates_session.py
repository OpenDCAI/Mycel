"""FS wrapper should count as activity (touch ChatSession) for idle reaper."""

import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from sandbox.manager import SandboxManager
from sandbox.provider import Metrics, ProviderCapability, ProviderExecResult, SandboxProvider, SessionInfo


class _FakeProvider(SandboxProvider):
    name = "fake"

    def __init__(self) -> None:
        self._statuses: dict[str, str] = {}

    def get_capability(self) -> ProviderCapability:
        return ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
            supports_webhook=False,
        )

    def create_session(self, context_id: str | None = None) -> SessionInfo:
        sid = f"s-{uuid.uuid4().hex[:8]}"
        self._statuses[sid] = "running"
        return SessionInfo(session_id=sid, provider=self.name, status="running")

    def destroy_session(self, session_id: str, sync: bool = True) -> bool:
        self._statuses.pop(session_id, None)
        return True

    def pause_session(self, session_id: str) -> bool:
        self._statuses[session_id] = "paused"
        return True

    def resume_session(self, session_id: str) -> bool:
        self._statuses[session_id] = "running"
        return True

    def get_session_status(self, session_id: str) -> str:
        return self._statuses.get(session_id, "deleted")

    def execute(
        self, session_id: str, command: str, timeout_ms: int = 30000, cwd: str | None = None
    ) -> ProviderExecResult:
        return ProviderExecResult(output="", exit_code=0)

    def read_file(self, session_id: str, path: str) -> str:
        return ""

    def write_file(self, session_id: str, path: str, content: str) -> str:
        return "ok"

    def list_dir(self, session_id: str, path: str) -> list[dict]:
        return [{"name": "a.txt", "type": "file", "size": 1}]

    def get_metrics(self, session_id: str) -> Metrics | None:
        return None

    def create_runtime(self, terminal, lease):
        from sandbox.runtime import RemoteWrappedRuntime
        return RemoteWrappedRuntime(terminal, lease, self)


def _temp_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        return Path(f.name)


def test_fs_list_dir_touches_session_last_active_at() -> None:
    db = _temp_db()
    try:
        provider = _FakeProvider()
        mgr = SandboxManager(provider=provider, db_path=db)

        cap = mgr.get_sandbox("thread-1")
        session_id = cap._session.session_id  # type: ignore[attr-defined]

        with sqlite3.connect(str(db)) as conn:
            before = conn.execute(
                "SELECT last_active_at FROM chat_sessions WHERE chat_session_id = ?",
                (session_id,),
            ).fetchone()[0]

        cap.fs.list_dir("/")

        with sqlite3.connect(str(db)) as conn:
            after = conn.execute(
                "SELECT last_active_at FROM chat_sessions WHERE chat_session_id = ?",
                (session_id,),
            ).fetchone()[0]

        assert datetime.fromisoformat(str(after)) >= datetime.fromisoformat(str(before))
    finally:
        db.unlink(missing_ok=True)
