from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import sandbox.capability as capability_module
import sandbox.runtime as runtime_module
from sandbox.capability import SandboxCapability
from sandbox.interfaces.executor import AsyncCommand, ExecuteResult
from sandbox.runtime import RemoteWrappedRuntime


class _FakeCommandRepo:
    def __init__(self):
        self.upserts: list[dict] = []
        self.chunks: list[dict] = []
        self.command_rows: dict[tuple[str, str], dict] = {}
        self.command_chunks: dict[str, list[dict]] = {}
        self.command_terminals: dict[tuple[str, str], str] = {}

    def upsert_command(
        self,
        *,
        command_id: str,
        terminal_id: str,
        chat_session_id: str | None,
        command_line: str,
        cwd: str,
        status: str,
        stdout: str,
        stderr: str,
        exit_code: int | None,
        updated_at: str,
        finished_at: str | None,
        created_at: str | None = None,
    ) -> None:
        row = {
            "command_id": command_id,
            "terminal_id": terminal_id,
            "chat_session_id": chat_session_id,
            "command_line": command_line,
            "cwd": cwd,
            "status": status,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "updated_at": updated_at,
            "finished_at": finished_at,
            "created_at": created_at or updated_at,
        }
        self.upserts.append(row)
        self.command_rows[(command_id, terminal_id)] = row

    def append_command_chunks(self, *, command_id: str, stdout_chunks: list[str], stderr_chunks: list[str], created_at: str) -> None:
        self.chunks.append(
            {
                "command_id": command_id,
                "stdout_chunks": list(stdout_chunks),
                "stderr_chunks": list(stderr_chunks),
                "created_at": created_at,
            }
        )
        bucket = self.command_chunks.setdefault(command_id, [])
        bucket.extend({"stream": "stdout", "content": chunk} for chunk in stdout_chunks)
        bucket.extend({"stream": "stderr", "content": chunk} for chunk in stderr_chunks)

    def get_command(self, *, command_id: str, terminal_id: str) -> dict | None:
        return self.command_rows.get((command_id, terminal_id))

    def list_command_chunks(self, *, command_id: str) -> list[dict]:
        return list(self.command_chunks.get(command_id, []))

    def find_command_terminal_id(self, *, command_id: str, thread_id: str) -> str | None:
        return self.command_terminals.get((command_id, thread_id))


class _FakeTerminal:
    terminal_id = "term-1"
    thread_id = "thread-1"

    def get_state(self):
        return SimpleNamespace(cwd="/tmp", env_delta={}, state_version=0)


class _FakeRuntime:
    def __init__(self, status: AsyncCommand | None = None):
        self.status = status

    async def start_command(self, command: str, cwd: str) -> AsyncCommand:
        raise AssertionError("not used in this test")

    async def get_command(self, command_id: str) -> AsyncCommand | None:
        return self.status

    async def wait_for_command(self, command_id: str, timeout: float | None = None) -> ExecuteResult | None:
        raise AssertionError("not used in this test")


class _FakeSession:
    def __init__(self, *, terminal_id: str, thread_id: str, runtime, command_repo: _FakeCommandRepo):
        self.thread_id = thread_id
        self.terminal = SimpleNamespace(terminal_id=terminal_id, get_state=lambda: SimpleNamespace(cwd="/tmp"))
        self.runtime = runtime
        self._session_repo = command_repo
        self.touches = 0

    def touch(self):
        self.touches += 1


def test_runtime_store_completed_result_uses_bound_command_repo_without_terminal_db_path():
    repo = _FakeCommandRepo()
    runtime = RemoteWrappedRuntime(_FakeTerminal(), SimpleNamespace(), SimpleNamespace())
    runtime.bind_session("sess-1")
    runtime.bind_command_repo(repo)

    runtime.store_completed_result(
        "cmd-1",
        "echo hi",
        "/tmp",
        ExecuteResult(exit_code=0, stdout="ok", stderr=""),
    )

    assert repo.upserts
    assert repo.upserts[0]["command_id"] == "cmd-1"
    assert repo.upserts[0]["terminal_id"] == "term-1"


@pytest.mark.asyncio
async def test_runtime_get_command_uses_bound_command_repo_without_terminal_db_path():
    repo = _FakeCommandRepo()
    repo.command_rows[("cmd-1", "term-1")] = {
        "command_id": "cmd-1",
        "command_line": "echo hi",
        "cwd": "/tmp",
        "status": "done",
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
    }
    repo.command_chunks["cmd-1"] = [
        {"stream": "stdout", "content": "hello "},
        {"stream": "stdout", "content": "world"},
    ]

    runtime = RemoteWrappedRuntime(_FakeTerminal(), SimpleNamespace(), SimpleNamespace())
    runtime.bind_command_repo(repo)

    status = await runtime.get_command("cmd-1")

    assert status is not None
    assert status.done is True
    assert "".join(status.stdout_buffer) == "hello world"


@pytest.mark.asyncio
async def test_command_wrapper_resolves_foreign_command_via_bound_command_repo_without_db_path():
    repo = _FakeCommandRepo()
    repo.command_terminals[("cmd-foreign", "thread-1")] = "term-2"

    expected = AsyncCommand(
        command_id="cmd-foreign",
        command_line="echo hi",
        cwd="/tmp",
        stdout_buffer=["ok"],
        stderr_buffer=[""],
        exit_code=0,
        done=True,
    )
    other_session = _FakeSession(
        terminal_id="term-2",
        thread_id="thread-1",
        runtime=_FakeRuntime(status=expected),
        command_repo=repo,
    )
    manager = SimpleNamespace(
        session_manager=SimpleNamespace(get=lambda thread_id, terminal_id: other_session),
    )
    session = _FakeSession(
        terminal_id="term-1",
        thread_id="thread-1",
        runtime=_FakeRuntime(),
        command_repo=repo,
    )

    capability = SandboxCapability(session, manager=manager)

    status = await capability.command.get_status("cmd-foreign")

    assert status is expected


def test_runtime_store_completed_result_requires_command_repo_for_strategy_default_terminal(monkeypatch):
    canonical_db = Path("/tmp/strategy-sandbox.db")
    monkeypatch.setattr(runtime_module, "uses_supabase_runtime_defaults", lambda: True, raising=False)
    monkeypatch.setattr(runtime_module, "resolve_role_db_path", lambda role: canonical_db, raising=False)
    monkeypatch.setattr(
        runtime_module,
        "connect_sqlite",
        lambda db_path: (_ for _ in ()).throw(AssertionError(f"sqlite fallback hit for {db_path}")),
    )

    terminal = _FakeTerminal()
    terminal.db_path = canonical_db
    runtime = RemoteWrappedRuntime(terminal, SimpleNamespace(), SimpleNamespace())

    with pytest.raises(RuntimeError, match="command repo"):
        runtime.store_completed_result(
            "cmd-1",
            "echo hi",
            "/tmp",
            ExecuteResult(exit_code=0, stdout="ok", stderr=""),
        )


@pytest.mark.asyncio
async def test_command_wrapper_requires_command_repo_for_strategy_default_lookup(monkeypatch):
    canonical_db = Path("/tmp/strategy-sandbox.db")
    monkeypatch.setattr(capability_module, "uses_supabase_runtime_defaults", lambda: True, raising=False)
    monkeypatch.setattr(capability_module, "resolve_role_db_path", lambda role: canonical_db, raising=False)
    monkeypatch.setattr(
        capability_module,
        "connect_sqlite",
        lambda db_path: (_ for _ in ()).throw(AssertionError(f"sqlite fallback hit for {db_path}")),
    )

    session = SimpleNamespace(
        thread_id="thread-1",
        terminal=SimpleNamespace(terminal_id="term-1", db_path=canonical_db, get_state=lambda: SimpleNamespace(cwd="/tmp")),
        runtime=_FakeRuntime(),
        touch=lambda: None,
    )
    capability = SandboxCapability(session)

    with pytest.raises(RuntimeError, match="command repo"):
        await capability.command.get_status("cmd-missing")
