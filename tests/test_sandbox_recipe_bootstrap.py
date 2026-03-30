from __future__ import annotations

import sqlite3
import tempfile
import uuid
from pathlib import Path

from sandbox.manager import SandboxManager
from sandbox.provider import Metrics, ProviderCapability, ProviderExecResult, SandboxProvider, SessionInfo


class BootstrapProbeProvider(SandboxProvider):
    name = "fake"

    def __init__(self):
        self._statuses: dict[str, str] = {}
        self.commands: list[str] = []
        self._has_lark_cli = False

    def get_capability(self) -> ProviderCapability:
        return ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
            supports_webhook=False,
        )

    def create_session(self, context_id: str | None = None, thread_id: str | None = None) -> SessionInfo:
        sid = context_id or f"s-{uuid.uuid4().hex[:8]}"
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
        self,
        session_id: str,
        command: str,
        timeout_ms: int = 30000,
        cwd: str | None = None,
    ) -> ProviderExecResult:
        self.commands.append(command)
        if command == "command -v lark-cli":
            if self._has_lark_cli:
                return ProviderExecResult(output="/usr/local/bin/lark-cli\n", exit_code=0)
            return ProviderExecResult(output="", exit_code=1)
        if command == "npm install -g @larksuite/cli":
            self._has_lark_cli = True
            return ProviderExecResult(output="installed", exit_code=0)
        return ProviderExecResult(output="", exit_code=0)

    def read_file(self, session_id: str, path: str) -> str:
        return ""

    def write_file(self, session_id: str, path: str, content: str) -> str:
        return "ok"

    def list_dir(self, session_id: str, path: str) -> list[dict]:
        return []

    def get_metrics(self, session_id: str) -> Metrics | None:
        return None

    def create_runtime(self, terminal, lease):
        from sandbox.runtime import RemoteWrappedRuntime
        return RemoteWrappedRuntime(terminal, lease, self)


def _temp_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        return Path(f.name)


def test_recipe_bootstrap_runs_once_when_session_is_created() -> None:
    db = _temp_db()
    try:
        provider = BootstrapProbeProvider()
        mgr = SandboxManager(provider=provider, db_path=db)
        lease = mgr.lease_store.create("lease-bootstrap", provider.name)
        lease_id = str(lease["lease_id"])
        with sqlite3.connect(str(db)) as conn:
            conn.execute(
                "UPDATE sandbox_leases SET recipe_id = ?, recipe_json = ? WHERE lease_id = ?",
                (
                    "fake:default",
                    '{"id":"fake:default","name":"Fake Default","provider_name":"fake","provider_type":"fake","features":{"lark_cli":true}}',
                    lease_id,
                ),
            )
            conn.commit()
        mgr.terminal_store.create("term-bootstrap", "thread-bootstrap", lease_id, "/tmp")
        mgr._setup_mounts = lambda _thread_id: {"source": None, "remote_path": "/tmp"}
        mgr._sync_to_sandbox = lambda *args, **kwargs: None

        _ = mgr.get_sandbox("thread-bootstrap")
        _ = mgr.get_sandbox("thread-bootstrap")

        assert provider.commands.count("command -v lark-cli") == 1
        assert provider.commands.count("npm install -g @larksuite/cli") == 1
    finally:
        db.unlink(missing_ok=True)
