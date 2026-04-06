"""Tests for CommandMiddleware."""

import asyncio
from dataclasses import dataclass

import pytest

from core.runtime.registry import ToolRegistry
from core.tools.command.base import AsyncCommand, BaseExecutor, ExecuteResult
from core.tools.command.dispatcher import get_executor, get_shell_info
from core.tools.command.hooks.dangerous_commands import DangerousCommandsHook
from core.tools.command.middleware import CommandMiddleware
from core.tools.command.service import CommandService


class TestExecuteResult:
    def test_success(self):
        result = ExecuteResult(exit_code=0, stdout="hello", stderr="")
        assert result.success
        assert result.output == "hello"
        assert result.to_tool_result() == "hello"

    def test_failure(self):
        result = ExecuteResult(exit_code=1, stdout="", stderr="error")
        assert not result.success
        assert "error" in result.output
        assert "Exit code: 1" in result.to_tool_result()

    def test_timeout(self):
        result = ExecuteResult(exit_code=-1, stdout="", stderr="", timed_out=True)
        assert not result.success
        assert "timed out" in result.to_tool_result().lower()


class TestDispatcher:
    def test_get_executor(self):
        executor = get_executor()
        assert executor is not None
        assert executor.shell_name in ("zsh", "bash", "powershell")

    def test_get_shell_info(self):
        info = get_shell_info()
        assert "os" in info
        assert "shell_name" in info
        assert "shell_path" in info


class TestExecutor:
    @pytest.mark.asyncio
    async def test_execute_echo(self):
        executor = get_executor()
        result = await executor.execute("echo hello")
        assert result.success
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_with_cwd(self, tmp_path):
        executor = get_executor()
        result = await executor.execute("pwd", cwd=str(tmp_path))
        assert result.success
        assert str(tmp_path) in result.stdout

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        executor = get_executor()
        result = await executor.execute("sleep 10", timeout=0.1)
        assert result.timed_out
        assert not result.success

    @pytest.mark.asyncio
    async def test_execute_nonexistent_command(self):
        executor = get_executor()
        result = await executor.execute("nonexistent_command_12345")
        assert not result.success
        assert result.exit_code != 0


class TestAsyncExecution:
    @pytest.mark.asyncio
    async def test_execute_async(self):
        executor = get_executor()
        async_cmd = await executor.execute_async("echo async_test")
        assert async_cmd.command_id is not None

        result = await executor.wait_for(async_cmd.command_id, timeout=5.0)
        assert result is not None
        assert result.success
        assert "async_test" in result.stdout

    @pytest.mark.asyncio
    async def test_get_status(self):
        executor = get_executor()
        command = "Start-Sleep -Milliseconds 100; Write-Output done" if executor.shell_name == "powershell" else "sleep 0.1 && echo done"
        async_cmd = await executor.execute_async(command)

        status = await executor.get_status(async_cmd.command_id)
        assert status is not None

        await asyncio.sleep(1.0)

        status = await executor.get_status(async_cmd.command_id)
        assert status is not None
        assert status.done


class TestDangerousCommandsHook:
    def test_block_rm_rf(self):
        hook = DangerousCommandsHook()
        result = hook.check_command("rm -rf /", {})
        assert not result.allow
        assert "SECURITY" in result.error_message

    def test_allow_dangerous_text_inside_quotes(self):
        hook = DangerousCommandsHook(verbose=False)
        result = hook.check_command('echo "rm -rf /"', {})
        assert result.allow

    def test_allow_dangerous_text_inside_comment(self):
        hook = DangerousCommandsHook(verbose=False)
        result = hook.check_command("echo hi # rm -rf /", {})
        assert result.allow

    def test_block_obfuscated_dangerous_command_name_with_inline_quotes(self):
        hook = DangerousCommandsHook(verbose=False)
        result = hook.check_command('s"u"do echo hi', {})
        assert not result.allow

    def test_block_obfuscated_file_mutation_command_name_with_inline_quotes(self):
        hook = DangerousCommandsHook(verbose=False)
        result = hook.check_command('ch"mo"d 777 /tmp/x', {})
        assert not result.allow

    def test_block_ansi_c_quoted_obfuscation(self):
        hook = DangerousCommandsHook(verbose=False)
        result = hook.check_command("s$'udo' echo hi", {})
        assert not result.allow

    def test_block_locale_quoted_obfuscation(self):
        hook = DangerousCommandsHook(verbose=False)
        result = hook.check_command('$"chmod" 777 /tmp/x', {})
        assert not result.allow

    def test_block_sudo(self):
        hook = DangerousCommandsHook()
        result = hook.check_command("sudo apt install", {})
        assert not result.allow

    def test_allow_safe_command(self):
        hook = DangerousCommandsHook()
        result = hook.check_command("echo hello", {})
        assert result.allow

    def test_block_network_when_enabled(self):
        hook = DangerousCommandsHook(block_network=True)
        result = hook.check_command("curl https://example.com", {})
        assert not result.allow

    def test_allow_network_when_disabled(self):
        hook = DangerousCommandsHook(block_network=False)
        result = hook.check_command("curl https://example.com", {})
        assert result.allow


class TestCommandMiddleware:
    def test_init(self, tmp_path):
        middleware = CommandMiddleware(workspace_root=tmp_path)
        assert middleware.workspace_root == tmp_path
        assert len(middleware.tools) == 2

    def test_init_with_hooks(self, tmp_path):
        hooks = [DangerousCommandsHook()]
        middleware = CommandMiddleware(workspace_root=tmp_path, hooks=hooks)
        assert len(middleware.hooks) == 1

    def test_check_hooks_block(self, tmp_path):
        hooks = [DangerousCommandsHook()]
        middleware = CommandMiddleware(workspace_root=tmp_path, hooks=hooks)
        allowed, error = middleware._check_hooks("rm -rf /")
        assert not allowed
        assert "SECURITY" in error

    def test_check_hooks_allow(self, tmp_path):
        hooks = [DangerousCommandsHook()]
        middleware = CommandMiddleware(workspace_root=tmp_path, hooks=hooks)
        allowed, error = middleware._check_hooks("echo hello")
        assert allowed
        assert error == ""


@dataclass
class _StatusFixture:
    status: AsyncCommand


class _StatusOnlyExecutor(BaseExecutor):
    runtime_owns_cwd = True
    shell_name = "bash"

    def __init__(self, fixture: _StatusFixture):
        super().__init__(default_cwd=None)
        self.fixture = fixture

    async def execute(self, command: str, cwd: str | None = None, timeout: float | None = None, env=None):
        raise NotImplementedError

    async def execute_async(self, command: str, cwd: str | None = None, env=None):
        raise NotImplementedError

    async def get_status(self, command_id: str):
        if command_id == self.fixture.status.command_id:
            return self.fixture.status
        return None

    async def wait_for(self, command_id: str, timeout: float | None = None):
        return None

    def store_completed_result(self, command_id: str, command_line: str, cwd: str, result: ExecuteResult) -> None:
        return None


class _BlankErrorExecutor(BaseExecutor):
    runtime_owns_cwd = True
    shell_name = "bash"

    class BlankCommandError(Exception):
        pass

    async def execute(self, command: str, cwd: str | None = None, timeout: float | None = None, env=None):
        raise self.BlankCommandError()

    async def execute_async(self, command: str, cwd: str | None = None, env=None):
        raise self.BlankCommandError()

    async def get_status(self, command_id: str):
        return None

    async def wait_for(self, command_id: str, timeout: float | None = None):
        return None

    def store_completed_result(self, command_id: str, command_line: str, cwd: str, result: ExecuteResult) -> None:
        return None


class TestCommandStatusFormatting:
    @pytest.mark.asyncio
    async def test_running_status_strips_pty_prompt_echo_noise(self, tmp_path):
        status = AsyncCommand(
            command_id="cmd_noise",
            command_line="for i in 1 2 3; do echo tick-$i; sleep 1; done",
            cwd=str(tmp_path),
            stdout_buffer=[
                "ffor i in 1 2 3; do echo tick-$i; sleep 1; done>\n",
                "tick-1\n",
            ],
            done=False,
        )
        executor = _StatusOnlyExecutor(_StatusFixture(status=status))
        middleware = CommandMiddleware(workspace_root=tmp_path, executor=executor, verbose=False)

        out = await middleware._get_command_status("cmd_noise", wait_seconds=0)
        assert "Status: running" in out
        assert "tick-1" in out
        assert "ffor i in 1 2 3" not in out

    @pytest.mark.asyncio
    async def test_running_status_includes_stderr_chunks(self, tmp_path):
        status = AsyncCommand(
            command_id="cmd_stderr",
            command_line='python -c \'import sys,time; print("out"); sys.stderr.write("err\\n"); time.sleep(3)\'',
            cwd=str(tmp_path),
            stdout_buffer=["out\n"],
            stderr_buffer=["err\n"],
            done=False,
        )
        executor = _StatusOnlyExecutor(_StatusFixture(status=status))
        middleware = CommandMiddleware(workspace_root=tmp_path, executor=executor, verbose=False)

        out = await middleware._get_command_status("cmd_stderr", wait_seconds=0)
        assert "Status: running" in out
        output_block = out.split("Output so far:\n", 1)[1]
        assert "out" in output_block
        assert "err" in output_block


class TestFailLoudBlankExceptions:
    @pytest.mark.asyncio
    async def test_command_middleware_surfaces_exception_type_when_message_is_blank(self, tmp_path):
        middleware = CommandMiddleware(workspace_root=tmp_path, executor=_BlankErrorExecutor(), verbose=False)

        out = await middleware._execute_blocking("pwd", str(tmp_path), timeout=1)

        assert out == "Error executing command: BlankCommandError"

    @pytest.mark.asyncio
    async def test_command_service_surfaces_exception_type_when_message_is_blank(self, tmp_path):
        service = CommandService(
            registry=ToolRegistry(),
            workspace_root=tmp_path,
            executor=_BlankErrorExecutor(),
        )

        out = await service._bash("pwd")

        assert out == "Error executing command: BlankCommandError"
