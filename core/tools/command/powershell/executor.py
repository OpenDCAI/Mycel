"""PowerShell executor implementation for Windows."""

from __future__ import annotations

import asyncio
import os
import uuid

from ..base import AsyncCommand, BaseExecutor, ExecuteResult

_RUNNING_COMMANDS: dict[str, AsyncCommand] = {}


class PowerShellExecutor(BaseExecutor):
    """Executor for PowerShell (Windows default)."""

    shell_name = "powershell"
    shell_command = ("powershell.exe", "-Command")

    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        work_dir = cwd or self.default_cwd or os.getcwd()

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        try:
            proc = await asyncio.create_subprocess_exec(
                self.shell_command[0],
                self.shell_command[1],
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env=merged_env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
                return ExecuteResult(
                    exit_code=proc.returncode or 0,
                    stdout=stdout_bytes.decode("utf-8", errors="replace"),
                    stderr=stderr_bytes.decode("utf-8", errors="replace"),
                    timed_out=False,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return ExecuteResult(
                    exit_code=-1,
                    stdout="",
                    stderr=f"Command timed out after {timeout}s",
                    timed_out=True,
                )

        except FileNotFoundError:
            return ExecuteResult(
                exit_code=127,
                stdout="",
                stderr=f"Shell not found: {self.shell_command[0]}",
            )
        except PermissionError:
            return ExecuteResult(
                exit_code=126,
                stdout="",
                stderr=f"Permission denied: {command}",
            )
        except OSError as e:
            return ExecuteResult(
                exit_code=1,
                stdout="",
                stderr=f"OS error: {e}",
            )

    async def execute_async(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncCommand:
        work_dir = cwd or self.default_cwd or os.getcwd()
        command_id = f"cmd_{uuid.uuid4().hex[:12]}"

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        proc = await asyncio.create_subprocess_exec(
            self.shell_command[0],
            self.shell_command[1],
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env=merged_env,
        )

        async_cmd = AsyncCommand(
            command_id=command_id,
            command_line=command,
            cwd=work_dir,
            process=proc,
        )
        _RUNNING_COMMANDS[command_id] = async_cmd

        asyncio.create_task(self._monitor_process(async_cmd))

        return async_cmd

    async def _monitor_process(self, async_cmd: AsyncCommand) -> None:
        """Background task to monitor process and collect output."""
        proc = async_cmd.process
        if proc is None:
            return

        stdout_bytes, stderr_bytes = await proc.communicate()

        async_cmd.stdout_buffer.append(stdout_bytes.decode("utf-8", errors="replace"))
        async_cmd.stderr_buffer.append(stderr_bytes.decode("utf-8", errors="replace"))
        async_cmd.exit_code = proc.returncode
        async_cmd.done = True

    async def get_status(self, command_id: str) -> AsyncCommand | None:
        return _RUNNING_COMMANDS.get(command_id)

    async def wait_for(
        self,
        command_id: str,
        timeout: float | None = None,
    ) -> ExecuteResult | None:
        async_cmd = _RUNNING_COMMANDS.get(command_id)
        if async_cmd is None:
            return None

        if not async_cmd.done:
            try:
                await asyncio.wait_for(
                    self._wait_until_done(async_cmd),
                    timeout=timeout,
                )
            except TimeoutError:
                return ExecuteResult(
                    exit_code=-1,
                    stdout="".join(async_cmd.stdout_buffer),
                    stderr="".join(async_cmd.stderr_buffer),
                    timed_out=True,
                    command_id=command_id,
                )

        return ExecuteResult(
            exit_code=async_cmd.exit_code or 0,
            stdout="".join(async_cmd.stdout_buffer),
            stderr="".join(async_cmd.stderr_buffer),
            timed_out=False,
            command_id=command_id,
        )

    async def _wait_until_done(self, async_cmd: AsyncCommand) -> None:
        while not async_cmd.done:
            await asyncio.sleep(0.1)

    def store_completed_result(
        self,
        command_id: str,
        command_line: str,
        cwd: str,
        result: ExecuteResult,
    ) -> None:
        """Store a completed result for later retrieval."""
        async_cmd = AsyncCommand(
            command_id=command_id,
            command_line=command_line,
            cwd=cwd,
            process=None,
            stdout_buffer=[result.stdout],
            stderr_buffer=[result.stderr],
            exit_code=result.exit_code,
            done=True,
        )
        _RUNNING_COMMANDS[command_id] = async_cmd
