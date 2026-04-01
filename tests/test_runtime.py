"""Unit tests for PhysicalTerminalRuntime."""

import asyncio
import re
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sandbox.chat_session import ChatSessionManager
from sandbox.interfaces.executor import ExecuteResult
from sandbox.lease import SandboxInstance, lease_from_row
from sandbox.provider import ProviderExecResult
from sandbox.runtime import (
    LocalPersistentShellRuntime,
    RemoteWrappedRuntime,
    _extract_state_from_output,
    _normalize_pty_result,
)
from sandbox.terminal import TerminalState, terminal_from_row
from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo
from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink(missing_ok=True)


@pytest.fixture
def terminal_store(temp_db):
    """Create SQLiteTerminalRepo with temp database."""
    return SQLiteTerminalRepo(db_path=temp_db)


class _LeaseStoreCompat:
    """Thin wrapper: repo returns dicts, tests expect domain objects from create/get."""

    def __init__(self, repo: SQLiteLeaseRepo):
        self._repo = repo

    def create(self, lease_id, provider_name, **kw):
        row = self._repo.create(lease_id, provider_name, **kw)
        return lease_from_row(row, self._repo.db_path)

    def get(self, lease_id):
        row = self._repo.get(lease_id)
        return lease_from_row(row, self._repo.db_path) if row else None

    def __getattr__(self, name):
        return getattr(self._repo, name)


@pytest.fixture
def lease_store(temp_db):
    """Create SQLiteLeaseRepo with compat wrapper for tests."""
    return _LeaseStoreCompat(SQLiteLeaseRepo(db_path=temp_db))


@pytest.fixture
def mock_provider():
    """Create mock SandboxProvider."""
    provider = MagicMock()
    provider.name = "test-provider"
    return provider


def _wrap_remote_state_output(
    wrapped_command: str,
    command_stdout: str,
    *,
    cwd: str,
    env: dict[str, str] | None = None,
) -> str:
    start_match = re.search(r"__LEON_STATE_START_[a-f0-9]{8}__", wrapped_command)
    end_match = re.search(r"__LEON_STATE_END_[a-f0-9]{8}__", wrapped_command)
    if not start_match or not end_match:
        raise AssertionError("Wrapped command missing state markers")
    env_map = env or {"PWD": cwd, "PATH": "/usr/bin"}
    lines: list[str] = []
    if command_stdout:
        lines.append(command_stdout)
    lines.append(start_match.group(0))
    lines.append(cwd)
    lines.extend(f"{k}={v}" for k, v in env_map.items())
    lines.append(end_match.group(0))
    return "\n".join(lines) + "\n"


class TestLocalPersistentShellRuntime:
    """Test LocalPersistentShellRuntime."""

    @pytest.mark.asyncio
    async def test_execute_simple_command(self, terminal_store, lease_store):
        """Test executing a simple command."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/tmp"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        runtime = LocalPersistentShellRuntime(terminal, lease)

        result = await runtime.execute("echo 'hello world'")

        assert result.exit_code == 0
        assert "hello world" in result.stdout
        assert not result.timed_out

    @pytest.mark.asyncio
    async def test_execute_updates_cwd(self, terminal_store, lease_store):
        """Test that cwd is updated after command execution."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/tmp"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        runtime = LocalPersistentShellRuntime(terminal, lease)

        # Execute cd command
        await runtime.execute("cd /")

        # Verify cwd updated
        state = runtime.get_terminal_state()
        assert state.cwd == "/"

    @pytest.mark.asyncio
    async def test_state_persists_across_commands(self, terminal_store, lease_store):
        """Test that state persists across multiple commands."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/tmp"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        runtime = LocalPersistentShellRuntime(terminal, lease)

        # Change directory
        await runtime.execute("cd /")
        assert runtime.get_terminal_state().cwd == "/"

        # Execute another command - should still be in /
        result = await runtime.execute("pwd")
        assert "/" in result.stdout.strip()

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self, terminal_store, lease_store):
        """Test command timeout."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/tmp"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        runtime = LocalPersistentShellRuntime(terminal, lease)

        # Execute long-running command with short timeout
        result = await runtime.execute("sleep 10", timeout=0.1)

        assert result.timed_out
        assert result.exit_code == -1

    @pytest.mark.asyncio
    async def test_close_terminates_session(self, terminal_store, lease_store):
        """Test that close terminates the shell session."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/tmp"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        runtime = LocalPersistentShellRuntime(terminal, lease)

        # Execute command to start session
        await runtime.execute("echo 'test'")
        assert runtime._pty_session is not None
        proc = runtime._pty_session.process

        # Close
        await runtime.close()

        # Session should be terminated
        assert proc is not None and proc.returncode is not None

    @pytest.mark.asyncio
    async def test_state_version_increments(self, terminal_store, lease_store):
        """Test that state version increments after updates."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/tmp"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        runtime = LocalPersistentShellRuntime(terminal, lease)

        assert runtime.get_terminal_state().state_version == 0

        # Execute command that changes cwd
        await runtime.execute("cd /")
        assert runtime.get_terminal_state().state_version == 1

        # Execute another command
        await runtime.execute("cd /tmp")
        assert runtime.get_terminal_state().state_version == 2


class TestRemoteWrappedRuntime:
    """Test RemoteWrappedRuntime."""

    @pytest.mark.asyncio
    async def test_execute_simple_command(self, terminal_store, lease_store, mock_provider):
        """Test executing a simple command via provider."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/root"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "test-provider")

        # Mock lease to return instance
        instance = SandboxInstance(
            instance_id="inst-123",
            provider_name="test-provider",
            status="running",
            created_at=None,
        )
        lease.ensure_active_instance = MagicMock(return_value=instance)

        def mock_execute(_instance_id, wrapped_command, **_kwargs):
            output = _wrap_remote_state_output(wrapped_command, "hello world", cwd="/root")
            return ProviderExecResult(exit_code=0, output=output, error=None)

        mock_provider.execute.side_effect = mock_execute

        runtime = RemoteWrappedRuntime(terminal, lease, mock_provider)

        result = await runtime.execute("echo 'hello world'")

        assert result.exit_code == 0
        assert result.stdout == "hello world"
        mock_provider.execute.assert_called()

    @pytest.mark.asyncio
    async def test_hydrate_state_on_first_execution(self, terminal_store, lease_store, mock_provider):
        """Test that state is hydrated on first execution."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/home/user"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "test-provider")

        # Mock lease to return instance
        instance = SandboxInstance(
            instance_id="inst-123",
            provider_name="test-provider",
            status="running",
            created_at=None,
        )
        lease.ensure_active_instance = MagicMock(return_value=instance)

        def mock_execute(_instance_id, wrapped_command, **_kwargs):
            output = _wrap_remote_state_output(wrapped_command, "", cwd="/home/user")
            return ProviderExecResult(exit_code=0, output=output, error=None)

        mock_provider.execute.side_effect = mock_execute

        runtime = RemoteWrappedRuntime(terminal, lease, mock_provider)

        await runtime.execute("echo 'test'")

        # Should have called cd to hydrate cwd
        calls = [str(call) for call in mock_provider.execute.call_args_list]
        assert any("cd /home/user" in str(call) for call in calls)

    @pytest.mark.asyncio
    async def test_execute_updates_cwd(self, terminal_store, lease_store, mock_provider):
        """Test that cwd is updated after command execution."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/root"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "test-provider")

        # Mock lease to return instance
        instance = SandboxInstance(
            instance_id="inst-123",
            provider_name="test-provider",
            status="running",
            created_at=None,
        )
        lease.ensure_active_instance = MagicMock(return_value=instance)

        # Mock provider execute
        def mock_execute(instance_id, command, **kwargs):
            start_match = re.search(r"__LEON_STATE_START_[a-f0-9]{8}__", command)
            end_match = re.search(r"__LEON_STATE_END_[a-f0-9]{8}__", command)
            if start_match and end_match:
                output = f"command output\n{start_match.group(0)}\n/home/user\nTEST_FLAG=1\n{end_match.group(0)}\n"
                return ProviderExecResult(exit_code=0, output=output, error=None)
            return ProviderExecResult(exit_code=0, output="", error=None)

        mock_provider.execute.side_effect = mock_execute

        runtime = RemoteWrappedRuntime(terminal, lease, mock_provider)

        await runtime.execute("cd /home/user")

        # Verify cwd updated
        state = runtime.get_terminal_state()
        assert state.cwd == "/home/user"

    @pytest.mark.asyncio
    async def test_close_is_noop(self, terminal_store, lease_store, mock_provider):
        """Test that close is a no-op for remote runtime."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/root"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "test-provider")

        runtime = RemoteWrappedRuntime(terminal, lease, mock_provider)

        # Close should not raise
        await runtime.close()

    @pytest.mark.asyncio
    async def test_infra_error_retries_once(self, terminal_store, lease_store, mock_provider):
        """Infra execution error should trigger one recovery retry."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/root"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "test-provider")

        instance = SandboxInstance(
            instance_id="inst-123",
            provider_name="test-provider",
            status="running",
            created_at=None,
        )
        lease.ensure_active_instance = MagicMock(return_value=instance)
        lease.refresh_instance_status = MagicMock(return_value="detached")

        execute_calls = 0

        def mock_execute(_instance_id, wrapped_command, **_kwargs):
            nonlocal execute_calls
            execute_calls += 1
            if execute_calls == 1:
                return ProviderExecResult(exit_code=1, output="", error="session not found")
            output = _wrap_remote_state_output(wrapped_command, "ok", cwd="/root")
            return ProviderExecResult(exit_code=0, output=output, error=None)

        mock_provider.execute.side_effect = mock_execute

        runtime = RemoteWrappedRuntime(terminal, lease, mock_provider)
        result = await runtime.execute("echo ok")

        assert result.exit_code == 0
        assert "ok" in result.stdout
        assert mock_provider.execute.call_count == 2
        assert lease.refresh_instance_status.call_count == 1

    @pytest.mark.asyncio
    async def test_non_infra_error_no_retry(self, terminal_store, lease_store, mock_provider):
        """Normal command failure should not trigger recovery retry."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/root"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "test-provider")

        instance = SandboxInstance(
            instance_id="inst-123",
            provider_name="test-provider",
            status="running",
            created_at=None,
        )
        lease.ensure_active_instance = MagicMock(return_value=instance)
        lease.refresh_instance_status = MagicMock(return_value="running")

        def mock_execute(_instance_id, wrapped_command, **_kwargs):
            output = _wrap_remote_state_output(wrapped_command, "grep: bad regex", cwd="/root")
            return ProviderExecResult(exit_code=2, output=output, error="")

        mock_provider.execute.side_effect = mock_execute

        runtime = RemoteWrappedRuntime(terminal, lease, mock_provider)
        result = await runtime.execute("grep")

        assert result.exit_code == 2
        assert mock_provider.execute.call_count == 1
        assert lease.refresh_instance_status.call_count == 0

    @pytest.mark.asyncio
    async def test_daytona_transient_no_ip_error_retries_once(self, terminal_store, lease_store, mock_provider):
        """Transient Daytona PTY bootstrap error should be treated as infra and retried once."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/root"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "test-provider")

        instance = SandboxInstance(
            instance_id="inst-123",
            provider_name="test-provider",
            status="running",
            created_at=None,
        )
        lease.ensure_active_instance = MagicMock(return_value=instance)
        lease.refresh_instance_status = MagicMock(return_value="running")

        execute_calls = 0

        def mock_execute(_instance_id, wrapped_command, **_kwargs):
            nonlocal execute_calls
            execute_calls += 1
            if execute_calls == 1:
                return ProviderExecResult(
                    exit_code=1,
                    output="",
                    error="Failed to create PTY session: bad request: no IP address found. Is the Sandbox started?",
                )
            output = _wrap_remote_state_output(wrapped_command, "ok", cwd="/root")
            return ProviderExecResult(exit_code=0, output=output, error=None)

        mock_provider.execute.side_effect = mock_execute

        runtime = RemoteWrappedRuntime(terminal, lease, mock_provider)
        result = await runtime.execute("echo ok")

        assert result.exit_code == 0
        assert "ok" in result.stdout
        assert mock_provider.execute.call_count == 2


class TestRuntimeIntegration:
    """Integration tests for runtime lifecycle."""

    @pytest.mark.asyncio
    async def test_local_runtime_full_lifecycle(self, terminal_store, lease_store):
        """Test complete local runtime lifecycle."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/tmp"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        runtime = LocalPersistentShellRuntime(terminal, lease)

        # Execute multiple commands
        result1 = await runtime.execute("echo 'first'")
        assert "first" in result1.stdout

        result2 = await runtime.execute("cd /")
        assert result2.exit_code == 0

        result3 = await runtime.execute("pwd")
        assert "/" in result3.stdout

        # Verify state persisted
        state = runtime.get_terminal_state()
        assert state.cwd == "/"
        # State version increments: initial=0, after first execute=1, after cd=2, after pwd=3
        assert state.state_version >= 2

        # Close
        await runtime.close()

    @pytest.mark.asyncio
    async def test_state_persists_across_runtime_instances(self, terminal_store, lease_store):
        """Test that terminal state persists when runtime is recreated."""
        terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/tmp"), terminal_store.db_path)
        lease = lease_store.create("lease-1", "local")

        # First runtime
        runtime1 = LocalPersistentShellRuntime(terminal, lease)
        await runtime1.execute("cd /")
        await runtime1.close()

        # Retrieve terminal again
        terminal2 = terminal_from_row(terminal_store.get_active("thread-1"), terminal_store.db_path)
        assert terminal2.get_state().cwd == "/"

        # Second runtime should start with persisted state
        runtime2 = LocalPersistentShellRuntime(terminal2, lease)
        result = await runtime2.execute("pwd")
        assert "/" in result.stdout

        await runtime2.close()


def test_docker_provider_create_runtime(terminal_store, lease_store):
    pytest.importorskip("docker")
    from sandbox.providers.docker import DockerProvider
    from sandbox.providers.docker import DockerPtyRuntime as DockerPtyRuntimeDirect

    terminal = terminal_from_row(terminal_store.create("term-1", "thread-1", "lease-1", "/tmp"), terminal_store.db_path)
    lease = lease_store.create("lease-1", "docker")
    provider = DockerProvider(image="ubuntu:latest", mount_path="/workspace")
    runtime = provider.create_runtime(terminal, lease)
    assert isinstance(runtime, DockerPtyRuntimeDirect)


def test_local_provider_create_runtime(terminal_store, lease_store):
    from sandbox.providers.local import LocalPersistentShellRuntime as LocalRuntimeDirect
    from sandbox.providers.local import LocalSessionProvider

    terminal = terminal_from_row(terminal_store.create("term-2", "thread-2", "lease-2", "/tmp"), terminal_store.db_path)
    lease = lease_store.create("lease-2", "local")
    provider = LocalSessionProvider()
    runtime = provider.create_runtime(terminal, lease)
    assert isinstance(runtime, LocalRuntimeDirect)


@pytest.mark.asyncio
async def test_daytona_runtime_streams_running_output(terminal_store, lease_store):
    terminal = terminal_from_row(terminal_store.create("term-2", "thread-2", "lease-2", "/tmp"), terminal_store.db_path)
    lease = lease_store.create("lease-2", "daytona")
    provider = MagicMock()
    from sandbox.providers.daytona import DaytonaSessionRuntime

    _runtime_instance = DaytonaSessionRuntime(terminal, lease, provider)
    provider.create_runtime.return_value = _runtime_instance
    ChatSessionManager(provider=provider, db_path=terminal_store.db_path)

    runtime = provider.create_runtime(terminal, lease)

    def _fake_execute_once(command: str, timeout: float | None = None, on_stdout_chunk=None):
        if on_stdout_chunk is not None:
            on_stdout_chunk("tick-1\n")
            time.sleep(0.2)
            on_stdout_chunk("tick-2\n")
        return ExecuteResult(exit_code=0, stdout="tick-1\ntick-2\n", stderr="")

    runtime._execute_once_sync = _fake_execute_once  # type: ignore[attr-defined]
    runtime._sync_terminal_state_snapshot_sync = lambda timeout=None: None  # type: ignore[attr-defined]

    async_cmd = await runtime.start_command("echo test", "/tmp")
    await asyncio.sleep(0.05)
    status = await runtime.get_command(async_cmd.command_id)
    assert status is not None
    assert "tick-1" in "".join(status.stdout_buffer)

    done = await runtime.wait_for_command(async_cmd.command_id, timeout=2.0)
    assert done is not None
    assert done.exit_code == 0
    assert "tick-2" in done.stdout
    with sqlite3.connect(str(terminal_store.db_path), timeout=30) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM terminal_command_chunks WHERE command_id = ?",
            (async_cmd.command_id,),
        ).fetchone()
    assert row is not None
    assert int(row[0]) >= 2
    await runtime.close()


@pytest.mark.asyncio
async def test_running_command_survives_runtime_reload_without_false_failure(terminal_store, lease_store):
    terminal = terminal_from_row(
        terminal_store.create("term-running-db", "thread-running-db", "lease-running-db", "/tmp"),
        terminal_store.db_path,
    )
    lease = lease_store.create("lease-running-db", "local")
    provider = MagicMock()
    from sandbox.providers.local import LocalPersistentShellRuntime

    provider.create_runtime.side_effect = lambda t, lease: LocalPersistentShellRuntime(t, lease)
    ChatSessionManager(provider=provider, db_path=terminal_store.db_path)

    runtime1 = provider.create_runtime(terminal, lease)
    async_cmd = await runtime1.start_command("for i in 1 2 3; do echo tick-$i; sleep 1; done", "/tmp")
    await asyncio.sleep(0.4)

    # Simulate command_status query from another runtime/session that has no in-memory task.
    runtime2 = provider.create_runtime(terminal, lease)
    status_running = await runtime2.get_command(async_cmd.command_id)
    assert status_running is not None
    assert not status_running.done
    assert "Runtime restarted before command completion" not in "".join(status_running.stderr_buffer)

    cross_wait = await runtime2.wait_for_command(async_cmd.command_id, timeout=5.0)
    assert cross_wait is not None
    assert cross_wait.exit_code == 0
    assert "tick-3" in cross_wait.stdout

    await runtime1.close()


@pytest.mark.asyncio
async def test_daytona_runtime_hydrates_once_per_pty_session(terminal_store, lease_store):
    pytest.importorskip("daytona_sdk")
    terminal = terminal_from_row(terminal_store.create("term-3", "thread-3", "lease-3", "/tmp"), terminal_store.db_path)
    lease = lease_store.create("lease-3", "daytona")
    instance = SandboxInstance(
        instance_id="inst-daytona-test",
        provider_name="daytona",
        status="running",
        created_at=None,
    )
    lease.ensure_active_instance = MagicMock(return_value=instance)  # type: ignore[method-assign]

    provider = MagicMock()
    from sandbox.providers.daytona import DaytonaSessionRuntime

    _daytona_runtime = DaytonaSessionRuntime(terminal, lease, provider)
    provider.create_runtime.return_value = _daytona_runtime
    ChatSessionManager(provider=provider, db_path=terminal_store.db_path)

    runtime = provider.create_runtime(terminal, lease)

    class _FakeHandle:
        def wait_for_connection(self, timeout=10.0):
            return None

        def disconnect(self):
            return None

        def send_input(self, _):
            return None

    fake_handle = _FakeHandle()

    class _FakeProcess:
        def connect_pty_session(self, _):
            return fake_handle

        def create_pty_session(self, **_kwargs):
            return fake_handle

        def kill_pty_session(self, _):
            return None

    class _FakeSandbox:
        process = _FakeProcess()

    runtime._provider_sandbox = lambda _instance_id: _FakeSandbox()  # type: ignore[attr-defined]

    init_count = 0

    def _fake_run(handle, command: str, timeout: float | None, on_stdout_chunk=None):
        nonlocal init_count
        if command.startswith("cd ") and "|| exit 1" in command:
            init_count += 1
            return "", "", 0
        if command == "env":
            return "PATH=/usr/bin\n", "", 0
        if "__LEON_STATE_START_" in command and "__LEON_STATE_END_" in command:
            start = re.search(r"__LEON_STATE_START_[a-f0-9]{8}__", command)
            end = re.search(r"__LEON_STATE_END_[a-f0-9]{8}__", command)
            assert start and end
            return f"{start.group(0)}\n/tmp\nPATH=/usr/bin\n{end.group(0)}\n", "", 0
        if on_stdout_chunk is not None:
            on_stdout_chunk("ok\n")
        return "ok\n", "", 0

    runtime._run_pty_command_sync = _fake_run  # type: ignore[attr-defined]

    result1 = await runtime.execute("echo first")
    result2 = await runtime.execute("echo second")
    assert result1.exit_code == 0
    assert result2.exit_code == 0

    # Let background snapshot complete.
    await asyncio.sleep(0.05)
    if runtime._snapshot_task is not None:  # type: ignore[attr-defined]
        await runtime._snapshot_task  # type: ignore[attr-defined]

    assert init_count == 1
    await runtime.close()


def test_extract_state_from_output_ignores_prompt_noise():
    start = "__LEON_STATE_START_deadbeef__"
    end = "__LEON_STATE_END_deadbeef__"
    raw = (
        "noise before\n"
        f"% prompt \x1b[0m{start}\n"
        "% abc\x08cd\n"
        "/home/daytona/snake-fullstack\n"
        "PWD=/home/daytona/snake-fullstack\n"
        "OLDPWD=/home/daytona\n"
        f"{end}\n"
        "noise after\n"
    )
    cwd, env_map, cleaned = _extract_state_from_output(
        raw,
        start,
        end,
        cwd_fallback="/home/daytona",
        env_fallback={},
    )
    assert cwd == "/home/daytona/snake-fullstack"
    assert env_map.get("PWD") == "/home/daytona/snake-fullstack"
    assert all("\x1b" not in key for key in env_map)
    assert start not in cleaned
    assert end not in cleaned


def test_normalize_pty_result_strips_prompt_echo_and_tail_prompt():
    output = (
        "%                                                                                                                        =eecho api-existing-thread-after-fix>\n"  # noqa: E501
        "api-existing-thread-after-fix\n"
        "%                                                                                                                        =pprintf '\\n__LEON_PTY_END_71d24aee__ %s\\n' $?>\n"  # noqa: E501
        "\n"
        "%                                                                                                                        \n"
    )
    cleaned = _normalize_pty_result(output, "echo api-existing-thread-after-fix")
    assert cleaned == "api-existing-thread-after-fix"


@pytest.mark.asyncio
async def test_daytona_runtime_sanitizes_corrupted_terminal_state_before_create(terminal_store, lease_store):
    pytest.importorskip("daytona_sdk")
    terminal = terminal_from_row(terminal_store.create("term-4", "thread-4", "lease-4", "/tmp"), terminal_store.db_path)
    # Simulate legacy-corrupted snapshot.
    terminal.update_state(
        TerminalState(
            cwd="\x1b>",
            env_delta={
                "% bad\x1b": "x",
                "PWD": "/home/daytona/snake-fullstack",
                "OLDPWD": "/home/daytona",
            },
        )
    )
    lease = lease_store.create("lease-4", "daytona")
    instance = SandboxInstance(
        instance_id="inst-daytona-sanitize",
        provider_name="daytona",
        status="running",
        created_at=None,
    )
    lease.ensure_active_instance = MagicMock(return_value=instance)  # type: ignore[method-assign]

    provider = MagicMock()
    from sandbox.providers.daytona import DaytonaSessionRuntime

    _daytona_runtime2 = DaytonaSessionRuntime(terminal, lease, provider)
    provider.create_runtime.return_value = _daytona_runtime2
    ChatSessionManager(provider=provider, db_path=terminal_store.db_path)
    runtime = provider.create_runtime(terminal, lease)

    created_kwargs: dict[str, object] = {}

    class _FakeHandle:
        def wait_for_connection(self, timeout=10.0):
            return None

        def disconnect(self):
            return None

        def send_input(self, _):
            return None

    fake_handle = _FakeHandle()

    class _FakeProcess:
        def connect_pty_session(self, _):
            raise RuntimeError("missing")

        def create_pty_session(self, **kwargs):
            created_kwargs.update(kwargs)
            return fake_handle

        def kill_pty_session(self, _):
            return None

    class _FakeSandbox:
        process = _FakeProcess()

    runtime._provider_sandbox = lambda _instance_id: _FakeSandbox()  # type: ignore[attr-defined]

    def _fake_run(_handle, command: str, timeout: float | None, on_stdout_chunk=None):
        if command == "env":
            return "PATH=/usr/bin\nPWD=/home/daytona/snake-fullstack\n", "", 0
        if "__LEON_STATE_START_" in command and "__LEON_STATE_END_" in command:
            start = re.search(r"__LEON_STATE_START_[a-f0-9]{8}__", command)
            end = re.search(r"__LEON_STATE_END_[a-f0-9]{8}__", command)
            assert start and end
            return (
                f"{start.group(0)}\n/home/daytona/snake-fullstack\nPWD=/home/daytona/snake-fullstack\n{end.group(0)}\n",
                "",
                0,
            )
        if on_stdout_chunk is not None:
            on_stdout_chunk("ok\n")
        return "ok\n", "", 0

    runtime._run_pty_command_sync = _fake_run  # type: ignore[attr-defined]

    result = await runtime.execute("echo test")
    assert result.exit_code == 0
    assert created_kwargs.get("cwd") == "/home/daytona/snake-fullstack"
    assert created_kwargs.get("envs") is None
    await runtime.close()
