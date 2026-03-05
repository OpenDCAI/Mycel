"""E2BPtyRuntime — E2B native SDK PTY handle for persistent shell."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from typing import TYPE_CHECKING

from sandbox.interfaces.executor import ExecuteResult
from sandbox.runtimes.base import (
    _extract_state_from_output,
    _normalize_pty_result,
    _parse_env_output,
    _sanitize_shell_output,
)
from sandbox.runtimes.wrapped import _RemoteRuntimeBase

if TYPE_CHECKING:
    from sandbox.lease import SandboxLease
    from sandbox.provider import SandboxProvider
    from sandbox.terminal import AbstractTerminal


class E2BPtyRuntime(_RemoteRuntimeBase):
    """E2B runtime using native SDK PTY handle for persistent shell."""

    def __init__(self, terminal: AbstractTerminal, lease: SandboxLease, provider: SandboxProvider):
        super().__init__(terminal, lease, provider)
        self._session_lock = asyncio.Lock()
        self._bound_instance_id: str | None = None
        self._pty_pid: int | None = None
        self._baseline_env: dict[str, str] | None = None

    @staticmethod
    def _extract_marker_exit(raw: str, marker: str, command: str | None = None) -> tuple[str, int]:
        exit_code = 0
        cleaned_lines: list[str] = []
        marker_re = re.compile(rf"{re.escape(marker)}\s+(-?\d+)")
        for line in raw.splitlines():
            m = marker_re.search(line)
            if m:
                exit_code = int(m.group(1))
                continue
            cleaned_lines.append(line)
        cleaned = _sanitize_shell_output("\n".join(cleaned_lines).strip())
        return _normalize_pty_result(cleaned, command), exit_code

    def _run_pty_command_sync(
        self,
        sandbox,
        pid: int,
        command: str,
        timeout: float | None,
    ) -> tuple[str, str, int]:
        marker = f"__LEON_PTY_END_{uuid.uuid4().hex[:8]}__"
        payload = f"{command}\nprintf '\\n{marker} %s\\n' $?\n"
        handle = sandbox.pty.connect(pid, timeout=timeout or 60)
        started = time.monotonic()
        raw = bytearray()
        try:
            sandbox.pty.send_stdin(pid, payload.encode("utf-8"))
            for _, _, pty_data in handle:
                if pty_data:
                    raw.extend(pty_data)
                    decoded = raw.decode("utf-8", errors="replace")
                    if marker in decoded:
                        cleaned, exit_code = self._extract_marker_exit(decoded, marker, command)
                        return cleaned, "", exit_code
                if timeout and time.monotonic() - started > timeout:
                    raise TimeoutError(f"Command timed out after {timeout}s")
            raise RuntimeError("PTY stream closed before marker")
        finally:
            handle.disconnect()

    def _ensure_shell_sync(self, timeout: float | None) -> tuple[object, int]:
        import shlex

        instance = self.lease.ensure_active_instance(self.provider)
        if self._bound_instance_id != instance.instance_id:
            self._bound_instance_id = instance.instance_id
            self._pty_pid = None
            self._baseline_env = None

        sandbox = self._provider_sandbox(instance.instance_id)

        if self._pty_pid is not None:
            try:
                processes = sandbox.commands.list()
                if any(getattr(proc, "pid", None) == self._pty_pid for proc in processes):
                    return sandbox, self._pty_pid
            except Exception:
                self._pty_pid = None

        from e2b.sandbox.commands.command_handle import PtySize

        state = self.terminal.get_state()
        handle = sandbox.pty.create(
            size=PtySize(rows=32, cols=120),
            cwd=state.cwd,
            timeout=0,
        )
        self._pty_pid = handle.pid
        handle.disconnect()
        self._run_pty_command_sync(sandbox, self._pty_pid, "export PS1=''; stty -echo", timeout)

        if state.env_delta:
            exports = "\n".join(f"export {k}={shlex.quote(v)}" for k, v in state.env_delta.items())
            if exports:
                self._run_pty_command_sync(sandbox, self._pty_pid, exports, timeout)

        baseline_out, _, _ = self._run_pty_command_sync(sandbox, self._pty_pid, "env", timeout)
        self._baseline_env = _parse_env_output(baseline_out)
        return sandbox, self._pty_pid

    def _execute_once_sync(self, command: str, timeout: float | None = None) -> ExecuteResult:
        import shlex

        sandbox, pid = self._ensure_shell_sync(timeout)
        state = self.terminal.get_state()
        stdout, stderr, exit_code = self._run_pty_command_sync(sandbox, pid, command, timeout)

        start_marker = f"__LEON_STATE_START_{uuid.uuid4().hex[:8]}__"
        end_marker = f"__LEON_STATE_END_{uuid.uuid4().hex[:8]}__"
        snapshot_out, _, _ = self._run_pty_command_sync(
            sandbox,
            pid,
            "\n".join([f"echo {shlex.quote(start_marker)}", "pwd", "env", f"echo {shlex.quote(end_marker)}"]),
            timeout,
        )
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

    async def execute(self, command: str, timeout: float | None = None) -> ExecuteResult:
        async with self._session_lock:
            try:
                return await asyncio.to_thread(self._execute_once_sync, command, timeout)
            except TimeoutError:
                return ExecuteResult(
                    exit_code=-1, stdout="", stderr=f"Command timed out after {timeout}s", timed_out=True
                )
            except Exception as exc:
                if self._looks_like_infra_error(str(exc)):
                    self._recover_infra()
                    self._pty_pid = None
                    try:
                        return await asyncio.to_thread(self._execute_once_sync, command, timeout)
                    except Exception as retry_exc:
                        return ExecuteResult(exit_code=1, stdout="", stderr=f"Error: {retry_exc}")
                return ExecuteResult(exit_code=1, stdout="", stderr=f"Error: {exc}")

    async def close(self) -> None:
        if self._pty_pid is None or self._bound_instance_id is None:
            return
        pid = self._pty_pid
        instance_id = self._bound_instance_id
        self._pty_pid = None
        try:
            sandbox = await asyncio.to_thread(self._provider_sandbox, instance_id)
            await asyncio.to_thread(sandbox.pty.kill, pid)
        except Exception:
            pass
