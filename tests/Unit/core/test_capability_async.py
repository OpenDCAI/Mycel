import asyncio
import inspect
import uuid
from pathlib import Path
from types import SimpleNamespace

import sandbox.capability as capability_module
from sandbox.base import LocalSandbox
from sandbox.capability import SandboxCapability
from sandbox.interfaces.executor import AsyncCommand, ExecuteResult
from sandbox.thread_context import set_current_thread_id


class _DummyState:
    cwd = "/tmp"


class _DummyTerminal:
    terminal_id = "dummy-term"

    def get_state(self):
        return _DummyState()


class _DummyRuntime:
    def __init__(self):
        self.commands: list[str] = []
        self._async_commands: dict[str, AsyncCommand] = {}

    async def execute(self, command: str, timeout=None):
        self.commands.append(command)
        await asyncio.sleep(0.01)
        return ExecuteResult(exit_code=0, stdout=f"ok:{command}", stderr="")

    async def start_command(self, command: str, cwd: str) -> AsyncCommand:
        command_id = f"cmd_{uuid.uuid4().hex[:12]}"
        result = await self.execute(command)
        async_cmd = AsyncCommand(
            command_id=command_id,
            command_line=command,
            cwd=cwd,
            exit_code=result.exit_code,
            done=True,
            stdout_buffer=[result.stdout],
        )
        self._async_commands[command_id] = async_cmd
        return async_cmd

    async def get_command(self, command_id: str) -> AsyncCommand | None:
        return self._async_commands.get(command_id)

    async def wait_for_command(self, command_id: str, timeout: float | None = None) -> ExecuteResult | None:
        cmd = self._async_commands.get(command_id)
        if cmd is None:
            return None
        return ExecuteResult(
            exit_code=cmd.exit_code or 0,
            stdout="".join(cmd.stdout_buffer),
            stderr="".join(cmd.stderr_buffer),
        )


class _DummySession:
    def __init__(self):
        self.terminal = _DummyTerminal()
        self.runtime = _DummyRuntime()
        self.touches = 0

    def touch(self):
        self.touches += 1


async def _run_async_command_flow():
    session = _DummySession()
    capability = SandboxCapability(session)

    async_cmd = await capability.command.execute_async("echo hi", cwd="/tmp/demo", env={"A": "1"})
    assert async_cmd.command_id.startswith("cmd_")

    status = await capability.command.get_status(async_cmd.command_id)
    assert status is not None

    result = await capability.command.wait_for(async_cmd.command_id, timeout=1.0)
    assert result is not None
    assert result.exit_code == 0
    assert "echo hi" in result.stdout
    assert session.touches > 0


def test_command_wrapper_supports_execute_async():
    asyncio.run(_run_async_command_flow())


def test_capability_doc_names_agent_facing_runtime_binding_surface():
    source = inspect.getsource(capability_module)
    guard_source = inspect.getsource(test_capability_doc_names_agent_facing_runtime_binding_surface)
    stale_chain = "Terminal \u2192 " + "Lease"
    stale_interface_label = "same " + "interface " + "as before"
    stale_interface_partial = "same " + "interface "

    assert stale_chain not in source
    assert stale_interface_label not in source
    assert stale_interface_partial not in source
    assert stale_interface_partial not in guard_source
    assert "agent-facing thread/runtime/sandbox binding surface" in source


def test_local_sandbox_rebuilds_stale_closed_capability_before_execute_async(tmp_path):
    root = Path(tmp_path)
    thread_id = "thread-stale-session"
    sandbox = LocalSandbox(str(root), db_path=root / "sandbox.db")
    set_current_thread_id(thread_id)
    capability = sandbox._get_capability()
    stale_session_id = capability._session.session_id
    sandbox.manager.session_manager.delete(stale_session_id, reason="test_close")

    async def run():
        async_cmd = await sandbox.shell().execute_async("echo hi")
        result = await sandbox.shell().wait_for(async_cmd.command_id, timeout=1.0)
        return async_cmd, result

    async_cmd, result = asyncio.run(run())

    assert capability._session.status == "closed"
    refreshed = sandbox._get_capability()
    assert refreshed._session.session_id != stale_session_id
    assert async_cmd.command_id.startswith("cmd_")
    assert result is not None
    assert result.exit_code == 0
    assert "hi" in result.stdout


def test_local_sandbox_close_destroys_only_owned_threads_without_global_inventory():
    class _Manager:
        def __init__(self):
            self.destroyed: list[str] = []

        def list_sessions(self):
            raise AssertionError("LocalSandbox.close must not scan shared session inventory")

        def destroy_session(self, thread_id: str):
            self.destroyed.append(thread_id)

    sandbox = object.__new__(LocalSandbox)
    sandbox._manager = _Manager()
    sandbox._capability_cache = {}
    sandbox._owned_thread_ids = {"thread-b", "thread-a"}

    sandbox.close()

    assert sandbox._manager.destroyed == ["thread-a", "thread-b"]


def test_local_sandbox_records_thread_id_when_building_capability():
    class _Manager:
        def __init__(self):
            self.requested: list[str] = []

        def get_sandbox(self, thread_id: str):
            self.requested.append(thread_id)
            return SimpleNamespace(_session=SimpleNamespace(session_id=f"sess-{thread_id}", status="active"))

    sandbox = object.__new__(LocalSandbox)
    sandbox._manager = _Manager()
    sandbox._capability_cache = {}
    sandbox._owned_thread_ids = set()

    set_current_thread_id("thread-owned")

    capability = sandbox._get_capability()

    assert capability._session.session_id == "sess-thread-owned"
    assert sandbox._manager.requested == ["thread-owned"]
    assert sandbox._owned_thread_ids == {"thread-owned"}


def test_filesystem_wrapper_auto_resumes_paused_lease_before_listing():
    class _PausedLease:
        def __init__(self):
            self.observed_state = "paused"

        def ensure_active_instance(self, _provider):
            if self.observed_state == "paused":
                raise RuntimeError("Sandbox lease lease-1 is paused. Resume before executing commands.")
            return SimpleNamespace(instance_id="inst-1")

    class _RemoteProvider:
        def list_dir(self, instance_id: str, path: str):
            assert instance_id == "inst-1"
            assert path == "/home/daytona"
            return [{"name": "demo.txt", "type": "file", "size": 7}]

    lease = _PausedLease()
    provider = _RemoteProvider()
    resume_calls: list[tuple[str, str]] = []

    class _RemoteSession:
        def __init__(self):
            self.thread_id = "thread-paused"
            self.terminal = _DummyTerminal()
            self.lease = lease
            self.runtime = SimpleNamespace(provider=provider)
            self.touches = 0

        def touch(self):
            self.touches += 1

    session = _RemoteSession()
    manager = SimpleNamespace(
        resume_session=lambda thread_id, source="user_resume": (
            resume_calls.append((thread_id, source)) or setattr(lease, "observed_state", "running") or True
        )
    )

    capability = SandboxCapability(session, manager=manager)

    result = capability.fs.list_dir("/home/daytona")

    assert resume_calls == [("thread-paused", "auto_resume")]
    assert [entry.name for entry in result.entries] == ["demo.txt"]
    assert result.error is None


def test_filesystem_wrapper_derives_remote_file_size_from_parent_listing():
    class _Lease:
        observed_state = "running"

        def ensure_active_instance(self, _provider):
            return SimpleNamespace(instance_id="inst-1")

    class _RemoteProvider:
        def list_dir(self, instance_id: str, path: str):
            assert instance_id == "inst-1"
            assert path == "/home/daytona"
            return [
                {"name": "demo.txt", "type": "file", "size": 42},
                {"name": "nested", "type": "directory", "size": 0},
            ]

    class _RemoteSession:
        def __init__(self):
            self.thread_id = "thread-size"
            self.terminal = _DummyTerminal()
            self.lease = _Lease()
            self.runtime = SimpleNamespace(provider=_RemoteProvider())
            self.touches = 0

        def touch(self):
            self.touches += 1

    capability = SandboxCapability(_RemoteSession())

    assert capability.fs.file_size("/home/daytona/demo.txt") == 42
    assert capability.fs.file_size("/home/daytona/missing.txt") is None
    assert capability.fs.file_size("/") is None
