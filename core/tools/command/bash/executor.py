"""Bash executor implementation with persistent shell session."""

from __future__ import annotations

import asyncio
import os
import uuid

from ..base import AsyncCommand, BaseExecutor, ExecuteResult

_RUNNING_COMMANDS: dict[str, AsyncCommand] = {}


class BashExecutor(BaseExecutor):
    """Executor for bash shell (Linux default) with persistent session."""

    shell_name = "bash"
    shell_command = ("/bin/bash",)

    def __init__(self, default_cwd: str | None = None):
        super().__init__(default_cwd)
        self._session: asyncio.subprocess.Process | None = None
        self._session_lock = asyncio.Lock()
        self._current_cwd = default_cwd or os.getcwd()

    async def _ensure_session(self, env: dict[str, str]) -> asyncio.subprocess.Process:
        """Ensure persistent shell session exists."""
        if self._session is None or self._session.returncode is not None:
            self._session = await asyncio.create_subprocess_exec(
                *self.shell_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self._current_cwd,
            )
            # Disable PS1 prompt
            self._session.stdin.write(b"export PS1=''\n")
            await self._session.stdin.drain()
        return self._session

    async def _send_command(self, proc: asyncio.subprocess.Process, command: str) -> tuple[str, str, int]:
        """Send command to persistent session and read output."""
        marker = f"__END_{uuid.uuid4().hex[:8]}__"
        full_cmd = f"{command}\necho {marker} $?\n"

        proc.stdin.write(full_cmd.encode())
        await proc.stdin.drain()

        stdout_lines = []
        exit_code = 0

        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            line_str = line.decode("utf-8", errors="replace")
            if marker in line_str:
                parts = line_str.split()
                if len(parts) >= 2:
                    try:
                        exit_code = int(parts[1])
                    except ValueError:
                        pass
                break
            stdout_lines.append(line_str)

        return "".join(stdout_lines), "", exit_code

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

        async with self._session_lock:
            try:
                proc = await self._ensure_session(merged_env)

                # Change directory if needed
                if work_dir != self._current_cwd:
                    await self._send_command(proc, f"cd '{work_dir}'")
                    self._current_cwd = work_dir

                stdout, stderr, exit_code = await asyncio.wait_for(
                    self._send_command(proc, command),
                    timeout=timeout,
                )
                return ExecuteResult(
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    timed_out=False,
                )
            except TimeoutError:
                return ExecuteResult(
                    exit_code=-1,
                    stdout="",
                    stderr=f"Command timed out after {timeout}s",
                    timed_out=True,
                )
            except Exception as e:
                return ExecuteResult(
                    exit_code=1,
                    stdout="",
                    stderr=f"Error: {e}",
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

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env=merged_env,
            shell=True,
            executable=self.shell_command[0],
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
