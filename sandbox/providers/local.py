"""LocalSessionProvider — in-process session provider for local sandbox."""

from __future__ import annotations

import os
import platform
import shlex
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from sandbox.provider import (
    Metrics,
    ProviderCapability,
    ProviderExecResult,
    SandboxProvider,
    SessionInfo,
    build_resource_capabilities,
)

if TYPE_CHECKING:
    from sandbox.lease import SandboxLease
    from sandbox.runtime import PhysicalTerminalRuntime
    from sandbox.terminal import AbstractTerminal


@dataclass
class LocalSessionProvider(SandboxProvider):
    """Local session provider with direct host access."""

    CATALOG_ENTRY = {"vendor": None, "description": "Direct host access", "provider_type": "local"}
    name: str = "local"
    CAPABILITY = ProviderCapability(
        can_pause=True,
        can_resume=True,
        can_destroy=True,
        supports_webhook=False,
        supports_status_probe=False,
        eager_instance_binding=True,
        inspect_visible=False,
        runtime_kind="local",
        resource_capabilities=build_resource_capabilities(
            filesystem=True,
            terminal=True,
            metrics=True,
            screenshot=False,
            web=False,
            process=False,
            hooks=False,
            mount=False,
        ),
    )
    default_cwd: str | None = None
    _session_states: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _state_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def get_capability(self) -> ProviderCapability:
        return self.CAPABILITY

    def create_session(self, context_id: str | None = None, thread_id: str | None = None) -> SessionInfo:
        session_id = context_id or f"local-{uuid.uuid4().hex[:12]}"
        with self._state_lock:
            self._session_states[session_id] = "running"
        return SessionInfo(session_id=session_id, provider="local", status="running")

    def destroy_session(self, session_id: str, sync: bool = True) -> bool:
        with self._state_lock:
            state = self._session_states.get(session_id)
            if state == "detached":
                return True
            self._session_states[session_id] = "detached"
        return True

    def pause_session(self, session_id: str) -> bool:
        with self._state_lock:
            # @@@local-provider-process-boundary - LocalSessionProvider state is in-memory only; in multi-worker
            # web backends the pause/resume request can land on a different process than the one that created
            # the session. For lease-bound local sessions (context_id like "leon-<lease_id>" or "local-..."),
            # treat missing in-memory state as "running" so pause/resume stays idempotent across processes.
            state = self._session_states.get(session_id)
            if state is None:
                if session_id.startswith(("leon-", "local-")):
                    state = "running"
                else:
                    return False
            if state == "detached":
                return False
            if state != "paused":
                self._session_states[session_id] = "paused"
        return True

    def resume_session(self, session_id: str) -> bool:
        with self._state_lock:
            state = self._session_states.get(session_id)
            if state is None:
                if session_id.startswith(("leon-", "local-")):
                    state = "running"
                else:
                    return False
            if state == "detached":
                return False
            if state != "running":
                self._session_states[session_id] = "running"
        return True

    def get_session_status(self, session_id: str) -> str:
        with self._state_lock:
            state = self._session_states.get(session_id)
            if state is None and session_id.startswith(("leon-", "local-")):
                return "running"
            return state or "detached"

    def execute(
        self,
        session_id: str,
        command: str,
        timeout_ms: int = 30000,
        cwd: str | None = None,
    ) -> ProviderExecResult:
        workdir = cwd or self.default_cwd or str(Path.cwd())
        if platform.system() == "Windows":
            result = subprocess.run(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(timeout_ms / 1000, 0.1),
                check=False,
                cwd=workdir,
            )
            output = result.stdout or ""
            if result.stderr:
                output = f"{output}\n{result.stderr}" if output else result.stderr
            return ProviderExecResult(output=output, exit_code=result.returncode)

        shell_cmd = f"cd {shlex.quote(workdir)} && {command}"
        result = subprocess.run(
            ["/bin/bash", "-lc", shell_cmd],
            capture_output=True,
            text=True,
            timeout=max(timeout_ms / 1000, 0.1),
            check=False,
        )
        output = result.stdout or ""
        if result.stderr:
            output = f"{output}\n{result.stderr}" if output else result.stderr
        return ProviderExecResult(output=output, exit_code=result.returncode)

    def read_file(self, session_id: str, path: str) -> str:
        return Path(path).read_text()

    def write_file(self, session_id: str, path: str, content: str) -> str:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Written: {path}"

    def list_dir(self, session_id: str, path: str) -> list[dict]:
        target = Path(path)
        if not target.exists() or not target.is_dir():
            return []
        items: list[dict] = []
        for child in target.iterdir():
            item_type = "directory" if child.is_dir() else "file"
            size = child.stat().st_size if child.exists() else 0
            items.append({"name": child.name, "type": item_type, "size": int(size)})
        return items

    def get_metrics(self, session_id: str) -> Metrics | None:
        if platform.system() != "Darwin":
            return self.get_metrics_via_commands(session_id)

        # @@@local-metrics-macos - use fast macOS-native commands; avoid 'top' which requires sampling delay.
        try:
            r = self.execute(
                session_id,
                "sysctl -n hw.ncpu; ps -A -o %cpu | awk 'NR>1{s+=$1} END{printf \"%g\", s}'",
                timeout_ms=5000,
            )
            cpu_percent = None
            if r.exit_code == 0:
                lines = r.output.strip().splitlines()
                ncpu = int(lines[0]) if lines else 1
                if len(lines) > 1 and lines[1]:
                    cpu_percent = float(lines[1]) / max(ncpu, 1)

            r = self.execute(session_id, "pagesize; sysctl -n hw.memsize; vm_stat", timeout_ms=5000)
            memory_used_mb, memory_total_mb = None, None
            if r.exit_code == 0:
                lines = r.output.strip().splitlines()
                page_size = int(lines[0]) if lines else 4096
                memory_total_mb = int(lines[1]) / 1024 / 1024 if len(lines) > 1 else None
                active = wired = compressor = 0
                for line in lines[2:]:
                    if "Pages active:" in line:
                        active = int(line.split()[-1].rstrip("."))
                    elif "Pages wired down:" in line:
                        wired = int(line.split()[-1].rstrip("."))
                    elif "Pages occupied by compressor:" in line:
                        compressor = int(line.split()[-1].rstrip("."))
                if memory_total_mb is not None:
                    memory_used_mb = (active + wired + compressor) * page_size / 1024 / 1024

            r = self.execute(session_id, "df -g / | awk 'NR==2{print $2 - $4, $2}'", timeout_ms=5000)
            disk_used_gb, disk_total_gb = None, None
            if r.exit_code == 0 and r.output.strip():
                parts = r.output.strip().split()
                disk_used_gb = float(parts[0]) if parts else None
                disk_total_gb = float(parts[1]) if len(parts) > 1 else None

            return Metrics(
                cpu_percent=cpu_percent,
                memory_used_mb=memory_used_mb,
                memory_total_mb=memory_total_mb,
                disk_used_gb=disk_used_gb,
                disk_total_gb=disk_total_gb,
            )
        except Exception:
            return None

    def create_runtime(self, terminal: AbstractTerminal, lease: SandboxLease) -> PhysicalTerminalRuntime:
        from sandbox.providers.local import LocalPersistentShellRuntime
        return LocalPersistentShellRuntime(terminal, lease)


# ── Runtime ──────────────────────────────────────────────────────────────────

import asyncio  # noqa: E402
from collections.abc import Callable  # noqa: E402

from sandbox.interfaces.executor import ExecuteResult  # noqa: E402
from sandbox.runtime import (  # noqa: E402
    PhysicalTerminalRuntime,
    _SubprocessPtySession,
    _build_export_block,
    _compute_env_delta,
    _extract_state_from_output,
    _parse_env_output,
)


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _build_windows_shell_script(
    command: str,
    *,
    cwd: str,
    env_delta: dict[str, str],
) -> tuple[str, str, str]:
    start = f"__LEON_STATE_START_{uuid.uuid4().hex[:8]}__"
    end = f"__LEON_STATE_END_{uuid.uuid4().hex[:8]}__"
    lines = [
        "$ErrorActionPreference = 'Continue'",
        f"Set-Location -LiteralPath {_ps_quote(cwd)}",
    ]
    for key, value in env_delta.items():
        lines.append(f"$env:{key} = {_ps_quote(str(value))}")
    lines.extend(
        [
            "& {",
            command,
            "}",
            "$leonExit = $LASTEXITCODE",
            "if ($null -eq $leonExit) { $leonExit = 0 }",
            f"Write-Output {_ps_quote(start)}",
            "(Get-Location).Path",
            'Get-ChildItem Env: | ForEach-Object { "{0}={1}" -f $_.Name, $_.Value }',
            f"Write-Output {_ps_quote(end)}",
            "exit $leonExit",
        ]
    )
    return start, end, "\n".join(lines)


class LocalPersistentShellRuntime(PhysicalTerminalRuntime):
    """Local persistent shell runtime (for local provider).

    Uses a persistent PTY-backed shell session.
    """

    def __init__(
        self,
        terminal,
        lease,
        shell_command: tuple[str, ...] = ("/bin/bash",),
    ):
        super().__init__(terminal, lease)
        self.shell_command = shell_command
        self._pty_session: _SubprocessPtySession | None = None
        self._session_lock = asyncio.Lock()
        self._baseline_env: dict[str, str] | None = None
        self._use_windows_shell = platform.system() == "Windows"

    def _ensure_session_sync(self, timeout: float | None) -> _SubprocessPtySession:
        if self._pty_session and self._pty_session.is_alive():
            return self._pty_session

        state = self.terminal.get_state()
        self._pty_session = _SubprocessPtySession(list(self.shell_command), cwd=state.cwd)
        self._pty_session.start()
        self._pty_session.run("export PS1=''; stty -echo", timeout)
        if state.env_delta:
            exports = _build_export_block(state.env_delta)
            if exports:
                self._pty_session.run(exports, timeout)
        baseline_out, _, _ = self._pty_session.run("env", timeout)
        self._baseline_env = _parse_env_output(baseline_out)
        return self._pty_session

    def _execute_windows_once_sync(
        self,
        command: str,
        timeout: float | None,
        on_stdout_chunk: Callable[[str], None] | None = None,
    ) -> ExecuteResult:
        if self.lease.observed_state == "paused":
            raise RuntimeError(f"Sandbox lease {self.lease.lease_id} is paused. Resume before executing commands.")

        state = self.terminal.get_state()
        start, end, script = _build_windows_shell_script(command, cwd=state.cwd, env_delta=state.env_delta)
        completed = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            cwd=state.cwd,
            env=os.environ.copy(),
        )
        env_fallback = dict(self._baseline_env or os.environ.copy())
        new_cwd, env_map, stdout = _extract_state_from_output(
            completed.stdout,
            start,
            end,
            cwd_fallback=state.cwd,
            env_fallback=env_fallback,
        )
        env_delta = _compute_env_delta(env_map, env_fallback, state.env_delta)

        from sandbox.terminal import TerminalState

        self.update_terminal_state(TerminalState(cwd=new_cwd, env_delta=env_delta))
        if on_stdout_chunk is not None and stdout:
            on_stdout_chunk(stdout)
        return ExecuteResult(
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=completed.stderr or "",
            timed_out=False,
        )

    def _execute_once_sync(
        self,
        command: str,
        timeout: float | None,
        on_stdout_chunk: Callable[[str], None] | None = None,
    ) -> ExecuteResult:
        if self._use_windows_shell:
            return self._execute_windows_once_sync(command, timeout, on_stdout_chunk=on_stdout_chunk)

        if self.lease.observed_state == "paused":
            raise RuntimeError(f"Sandbox lease {self.lease.lease_id} is paused. Resume before executing commands.")

        state = self.terminal.get_state()
        pty_session = self._ensure_session_sync(timeout)
        stdout, stderr, exit_code = pty_session.run(command, timeout, on_stdout_chunk=on_stdout_chunk)

        # Capture state snapshot after each command so new ChatSession can hydrate from DB.
        pwd_stdout, _, _ = pty_session.run("pwd", timeout)
        env_stdout, _, _ = pty_session.run("env", timeout)
        pwd_lines = [line.strip() for line in pwd_stdout.splitlines() if line.strip()]
        new_cwd = pwd_lines[-1] if pwd_lines else state.cwd
        env_map = _parse_env_output(env_stdout)
        env_delta = _compute_env_delta(env_map, self._baseline_env or {}, state.env_delta)

        if new_cwd:
            from sandbox.terminal import TerminalState

            self.update_terminal_state(TerminalState(cwd=new_cwd, env_delta=env_delta))

        return ExecuteResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
        )

    async def _execute_background_command(
        self,
        command: str,
        timeout: float | None,
        on_stdout_chunk: Callable[[str], None] | None = None,
    ) -> ExecuteResult:
        async with self._session_lock:
            try:
                return await asyncio.to_thread(self._execute_once_sync, command, timeout, on_stdout_chunk)
            except (TimeoutError, subprocess.TimeoutExpired):
                await self._recover_after_timeout()
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

    async def _recover_after_timeout(self) -> None:
        """Recover PTY session after a command timeout."""
        if self._use_windows_shell:
            return
        if self._pty_session is None:
            return
        recovered = await asyncio.to_thread(self._pty_session.interrupt_and_recover)
        if not recovered:
            await asyncio.to_thread(self._pty_session.close)
            self._pty_session = None

    async def execute(self, command: str, timeout: float | None = None) -> ExecuteResult:
        """Execute command in local shell."""
        return await self._execute_background_command(command, timeout=timeout)

    async def close(self) -> None:
        """Close the shell session."""
        if self._use_windows_shell:
            return
        if self._pty_session:
            await asyncio.to_thread(self._pty_session.close)
