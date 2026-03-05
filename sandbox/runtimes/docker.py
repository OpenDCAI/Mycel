"""DockerPtyRuntime — Docker container with persistent PTY shell."""

from __future__ import annotations

import asyncio
import shlex
from collections.abc import Callable
from typing import TYPE_CHECKING

from sandbox.interfaces.executor import ExecuteResult
from sandbox.runtimes.base import (
    _SubprocessPtySession,
    _extract_state_from_output,
    _parse_env_output,
)
from sandbox.runtimes.wrapped import _RemoteRuntimeBase

if TYPE_CHECKING:
    from sandbox.lease import SandboxLease
    from sandbox.provider import SandboxProvider
    from sandbox.terminal import AbstractTerminal


class DockerPtyRuntime(_RemoteRuntimeBase):
    """Docker runtime using a persistent PTY shell inside container."""

    def __init__(self, terminal: AbstractTerminal, lease: SandboxLease, provider: SandboxProvider):
        super().__init__(terminal, lease, provider)
        self._session_lock = asyncio.Lock()
        self._bound_instance_id: str | None = None
        self._pty_session: _SubprocessPtySession | None = None
        self._baseline_env: dict[str, str] | None = None

    def _close_shell_sync(self) -> None:
        if self._pty_session:
            self._pty_session.close()
        self._pty_session = None

    def _ensure_shell_sync(self, timeout: float | None) -> _SubprocessPtySession:
        instance = self.lease.ensure_active_instance(self.provider)
        if self._bound_instance_id != instance.instance_id:
            self._close_shell_sync()
            self._bound_instance_id = instance.instance_id
            self._baseline_env = None

        if self._pty_session and self._pty_session.is_alive():
            return self._pty_session

        state = self.terminal.get_state()
        self._pty_session = _SubprocessPtySession(["docker", "exec", "-it", instance.instance_id, "/bin/sh"])
        self._pty_session.start()
        self._pty_session.run("export PS1=''; stty -echo", timeout)
        self._pty_session.run(f"cd {shlex.quote(state.cwd)} || exit 1", timeout)
        if state.env_delta:
            exports = "\n".join(f"export {k}={shlex.quote(v)}" for k, v in state.env_delta.items())
            if exports:
                self._pty_session.run(exports, timeout)
        baseline_out, _, _ = self._pty_session.run("env", timeout)
        self._baseline_env = _parse_env_output(baseline_out)
        return self._pty_session

    def _execute_once_sync(
        self,
        command: str,
        timeout: float | None,
        on_stdout_chunk: Callable[[str], None] | None = None,
    ) -> ExecuteResult:
        session = self._ensure_shell_sync(timeout)
        state = self.terminal.get_state()
        stdout, stderr, exit_code = session.run(command, timeout, on_stdout_chunk=on_stdout_chunk)

        import uuid
        start_marker = f"__LEON_STATE_START_{uuid.uuid4().hex[:8]}__"
        end_marker = f"__LEON_STATE_END_{uuid.uuid4().hex[:8]}__"
        snapshot_cmd = "\n".join([f"echo {shlex.quote(start_marker)}", "pwd", "env", f"echo {shlex.quote(end_marker)}"])
        snapshot_out, _, _ = session.run(snapshot_cmd, timeout)
        new_cwd, env_map, _ = _extract_state_from_output(
            snapshot_out,
            start_marker,
            end_marker,
            cwd_fallback=state.cwd,
            env_fallback=state.env_delta,
        )
        baseline_env = self._baseline_env or {}
        persisted_keys = set(state.env_delta.keys())
        env_delta = {k: v for k, v in env_map.items() if baseline_env.get(k) != v or k in persisted_keys}
        from sandbox.terminal import TerminalState

        self.update_terminal_state(TerminalState(cwd=new_cwd, env_delta=env_delta))
        return ExecuteResult(exit_code=exit_code, stdout=stdout, stderr=stderr)

    async def _execute_background_command(
        self,
        command: str,
        timeout: float | None,
        on_stdout_chunk: Callable[[str], None] | None = None,
    ) -> ExecuteResult:
        async with self._session_lock:
            try:
                return await asyncio.to_thread(self._execute_once_sync, command, timeout, on_stdout_chunk)
            except TimeoutError:
                await self._recover_after_timeout()
                return ExecuteResult(
                    exit_code=-1, stdout="", stderr=f"Command timed out after {timeout}s", timed_out=True
                )
            except Exception as exc:
                if self._looks_like_infra_error(str(exc)):
                    self._recover_infra()
                    self._close_shell_sync()
                    try:
                        return await asyncio.to_thread(self._execute_once_sync, command, timeout, on_stdout_chunk)
                    except Exception as retry_exc:
                        return ExecuteResult(exit_code=1, stdout="", stderr=f"Error: {retry_exc}")
                return ExecuteResult(exit_code=1, stdout="", stderr=f"Error: {exc}")

    async def _recover_after_timeout(self) -> None:
        """Recover PTY session after a command timeout."""
        if self._pty_session is None:
            return
        recovered = await asyncio.to_thread(self._pty_session.interrupt_and_recover)
        if not recovered:
            await asyncio.to_thread(self._pty_session.close)
            self._pty_session = None

    async def execute(self, command: str, timeout: float | None = None) -> ExecuteResult:
        return await self._execute_background_command(command, timeout=timeout)

    async def close(self) -> None:
        await asyncio.to_thread(self._close_shell_sync)
