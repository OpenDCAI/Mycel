"""DaytonaSessionRuntime — Daytona native PTY session runtime."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

from sandbox.interfaces.executor import ExecuteResult
from sandbox.runtimes.base import (
    ENV_NAME_RE,
    _SubprocessPtySession,
    _extract_state_from_output,
    _parse_env_output,
    _sanitize_shell_output,
)
from sandbox.runtimes.wrapped import _RemoteRuntimeBase

if TYPE_CHECKING:
    from sandbox.lease import SandboxLease
    from sandbox.provider import SandboxProvider
    from sandbox.terminal import AbstractTerminal


class DaytonaSessionRuntime(_RemoteRuntimeBase):
    """Daytona runtime using native PTY session API (persistent terminal semantics)."""

    def __init__(self, terminal: AbstractTerminal, lease: SandboxLease, provider: SandboxProvider):
        super().__init__(terminal, lease, provider)
        self._session_lock = asyncio.Lock()
        self._pty_session_id = f"leon-pty-{terminal.terminal_id[-12:]}"
        self._bound_instance_id: str | None = None
        self._pty_handle = None
        self._hydrated = False
        self._baseline_env: dict[str, str] | None = None
        self._snapshot_task: asyncio.Task[None] | None = None
        self._snapshot_generation = 0
        self._snapshot_error: str | None = None

    def _sanitize_terminal_snapshot(self) -> tuple[str, dict[str, str]]:
        state = self.terminal.get_state()
        cleaned_env = {k: v for k, v in state.env_delta.items() if ENV_NAME_RE.match(k)}
        cleaned_cwd = state.cwd
        if not os.path.isabs(cleaned_cwd):
            pwd_hint = cleaned_env.get("PWD")
            if isinstance(pwd_hint, str) and os.path.isabs(pwd_hint):
                cleaned_cwd = pwd_hint
            else:
                raise RuntimeError(
                    f"Invalid terminal cwd snapshot for terminal {self.terminal.terminal_id}: {state.cwd!r}"
                )
        if cleaned_cwd != state.cwd or cleaned_env != state.env_delta:
            from sandbox.terminal import TerminalState

            # @@@daytona-state-sanitize - Legacy prompt noise can corrupt persisted cwd/env_delta and break PTY creation.
            # Normalize once here so new abstract terminals inherit only valid state.
            self.update_terminal_state(TerminalState(cwd=cleaned_cwd, env_delta=cleaned_env))
        return cleaned_cwd, cleaned_env

    def _close_shell_sync(self) -> None:
        if self._pty_handle is not None:
            try:
                self._pty_handle.disconnect()
            except Exception:
                pass
        self._pty_handle = None
        self._hydrated = False
        if not self._bound_instance_id:
            return
        try:
            sandbox = self._provider_sandbox(self._bound_instance_id)
            sandbox.process.kill_pty_session(self._pty_session_id)
        except Exception:
            pass

    @staticmethod
    def _read_pty_chunk_sync(handle, wait_sec: float) -> bytes | None:
        ws = getattr(handle, "_ws", None)
        if ws is None:
            raise RuntimeError("Daytona PTY websocket unavailable")
        try:
            message = ws.recv(timeout=wait_sec)
        except TimeoutError:
            return None
        except Exception as exc:
            raise RuntimeError(f"Daytona PTY read failed: {exc}") from exc

        if isinstance(message, bytes):
            return message

        text = str(message)
        try:
            control = json.loads(text)
        except Exception:
            return text.encode("utf-8", errors="replace")

        if isinstance(control, dict) and control.get("type") == "control":
            status = str(control.get("status") or "")
            if status == "error":
                error = str(control.get("error") or "unknown")
                raise RuntimeError(f"Daytona PTY control error: {error}")
            return b""

        return text.encode("utf-8", errors="replace")

    def _run_pty_command_sync(
        self,
        handle,
        command: str,
        timeout: float | None,
        on_stdout_chunk: Callable[[str], None] | None = None,
    ) -> tuple[str, str, int]:
        marker = f"__LEON_PTY_END_{uuid.uuid4().hex[:8]}__"
        marker_done_re = re.compile(rf"{re.escape(marker)}\s+-?\d+")
        payload = f"{command}\nprintf '\\n{marker} %s\\n' $?\n"
        handle.send_input(payload)

        raw = bytearray()
        emitted_raw_len = 0
        deadline = time.monotonic() + timeout if timeout else None
        while True:
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f"Command timed out after {timeout}s")
            wait_sec = 0.1 if deadline is None else max(0.0, min(0.1, deadline - time.monotonic()))
            chunk = self._read_pty_chunk_sync(handle, wait_sec)
            if chunk is None:
                continue
            if not chunk:
                continue
            raw.extend(chunk)
            decoded = raw.decode("utf-8", errors="replace")
            if marker_done_re.search(decoded):
                cleaned, exit_code = _SubprocessPtySession._extract_marker_exit(decoded, marker, command)
                return cleaned, "", exit_code
            if on_stdout_chunk is not None:
                if len(decoded) > emitted_raw_len:
                    delta_raw = decoded[emitted_raw_len:]
                    emitted_raw_len = len(decoded)
                    delta = _sanitize_shell_output(delta_raw)
                    if delta:
                        on_stdout_chunk(delta)

    def _ensure_session_sync(self, timeout: float | None):
        instance = self.lease.ensure_active_instance(self.provider)
        if self._bound_instance_id != instance.instance_id:
            self._close_shell_sync()
            self._bound_instance_id = instance.instance_id
            self._baseline_env = None
            self._hydrated = False

        sandbox = self._provider_sandbox(instance.instance_id)
        effective_cwd, effective_env = self._sanitize_terminal_snapshot()
        if self._pty_handle is None:
            from daytona_sdk.common.pty import PtySize

            try:
                handle = sandbox.process.connect_pty_session(self._pty_session_id)
                handle.wait_for_connection(timeout=10.0)
            except Exception:
                try:
                    handle = sandbox.process.create_pty_session(
                        id=self._pty_session_id,
                        cwd=effective_cwd,
                        envs=None,
                        pty_size=PtySize(rows=32, cols=120),
                    )
                except Exception as create_exc:
                    message = str(create_exc)
                    if "/usr/bin/zsh" in message:
                        # @@@daytona-shell-fail-loud - Do not silently override provider shell selection.
                        # Surface explicit infra error so snapshot/image shell mismatch is fixed at source.
                        raise RuntimeError(
                            "Daytona PTY bootstrap failed: provider requested /usr/bin/zsh but it is missing "
                            "in the sandbox image. Fix provider snapshot/image shell config."
                        ) from create_exc
                    raise
            self._pty_handle = handle

        if not self._hydrated:
            _, _, shell_exit = self._run_pty_command_sync(self._pty_handle, "export PS1=''; stty -echo", timeout)
            if shell_exit != 0:
                raise RuntimeError(f"Daytona PTY shell normalization failed (exit={shell_exit})")
            init_parts = [f"cd {shlex.quote(effective_cwd)} || exit 1"]
            init_parts.extend(f"export {k}={shlex.quote(v)}" for k, v in effective_env.items())
            init_command = "\n".join(part for part in init_parts if part)
            if init_command:
                _, _, init_exit = self._run_pty_command_sync(self._pty_handle, init_command, timeout)
                if init_exit != 0:
                    raise RuntimeError(f"Daytona PTY hydrate failed (exit={init_exit})")

            baseline_out, _, _ = self._run_pty_command_sync(self._pty_handle, "env", timeout)
            self._baseline_env = _parse_env_output(baseline_out)
            self._hydrated = True
        return self._pty_handle

    def _execute_once_sync(
        self,
        command: str,
        timeout: float | None = None,
        on_stdout_chunk: Callable[[str], None] | None = None,
    ) -> ExecuteResult:
        handle = self._ensure_session_sync(timeout)
        stdout, _, exit_code = self._run_pty_command_sync(handle, command, timeout, on_stdout_chunk=on_stdout_chunk)
        return ExecuteResult(exit_code=exit_code, stdout=stdout, stderr="")

    def _sync_terminal_state_snapshot_sync(self, timeout: float | None = None) -> None:
        # Snapshot must be able to run after infra recovery (PTY re-created), so always ensure a handle.
        handle = self._ensure_session_sync(timeout)
        state = self.terminal.get_state()
        start_marker = f"__LEON_STATE_START_{uuid.uuid4().hex[:8]}__"
        end_marker = f"__LEON_STATE_END_{uuid.uuid4().hex[:8]}__"
        snapshot_out, _, _ = self._run_pty_command_sync(
            handle,
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

    async def _snapshot_state_async(self, generation: int, timeout: float | None) -> None:
        async with self._session_lock:
            if generation != self._snapshot_generation:
                return
            try:
                await asyncio.to_thread(self._sync_terminal_state_snapshot_sync, timeout)
            except Exception as exc:
                message = str(exc)
                if self._looks_like_infra_error(message):
                    # @@@daytona-snapshot-retry - Snapshot can fail due to stale PTY websocket even if sandbox is running.
                    # Refresh infra truth once, re-create PTY, and retry exactly once.
                    try:
                        self._recover_infra()
                        self._close_shell_sync()
                        await asyncio.to_thread(self._sync_terminal_state_snapshot_sync, timeout)
                        self._snapshot_error = None
                        return
                    except Exception as retry_exc:
                        self._snapshot_error = str(retry_exc)
                        return
                self._snapshot_error = message

    def _schedule_snapshot(self, generation: int, timeout: float | None) -> None:
        if self._snapshot_task and not self._snapshot_task.done():
            self._snapshot_task.cancel()
        self._snapshot_task = asyncio.create_task(self._snapshot_state_async(generation, timeout))

    async def _execute_background_command(
        self,
        command: str,
        timeout: float | None,
        on_stdout_chunk: Callable[[str], None] | None = None,
    ) -> ExecuteResult:
        async with self._session_lock:
            if self._snapshot_error:
                if self._looks_like_infra_error(self._snapshot_error):
                    # @@@daytona-snapshot-recover - Do not wedge the terminal forever on a transient snapshot failure.
                    # Attempt infra recovery once, then proceed (a fresh snapshot will be scheduled after this command).
                    try:
                        self._recover_infra()
                        self._close_shell_sync()
                        self._snapshot_error = None
                    except Exception as exc:
                        return ExecuteResult(
                            exit_code=1,
                            stdout="",
                            stderr=f"Error: snapshot failed: {exc}",
                        )
                else:
                    return ExecuteResult(
                        exit_code=1, stdout="", stderr=f"Error: snapshot failed: {self._snapshot_error}"
                    )
            try:
                first = await asyncio.to_thread(self._execute_once_sync, command, timeout, on_stdout_chunk)
            except TimeoutError:
                return ExecuteResult(
                    exit_code=-1, stdout="", stderr=f"Command timed out after {timeout}s", timed_out=True
                )
            except Exception as exc:
                if not self._looks_like_infra_error(str(exc)):
                    return ExecuteResult(exit_code=1, stdout="", stderr=f"Error: {exc}")
                self._recover_infra()
                self._close_shell_sync()
                try:
                    return await asyncio.to_thread(self._execute_once_sync, command, timeout, on_stdout_chunk)
                except Exception as retry_exc:
                    return ExecuteResult(exit_code=1, stdout="", stderr=f"Error: {retry_exc}")

            if first.exit_code != 0 and self._looks_like_infra_error(first.stderr or first.stdout):
                self._recover_infra()
                self._close_shell_sync()
                try:
                    return await asyncio.to_thread(self._execute_once_sync, command, timeout, on_stdout_chunk)
                except Exception as retry_exc:
                    return ExecuteResult(exit_code=1, stdout="", stderr=f"Error: {retry_exc}")

            self._snapshot_generation += 1
            generation = self._snapshot_generation

        # @@@daytona-async-snapshot - state sync runs in background so command result streaming is not blocked.
        # @@@daytona-snapshot-timeout - Snapshot reads full env; don't inherit overly aggressive user timeouts.
        snapshot_timeout = None if timeout is None else max(float(timeout), 10.0)
        self._schedule_snapshot(generation, snapshot_timeout)
        return first

    async def execute(self, command: str, timeout: float | None = None) -> ExecuteResult:
        return await self._execute_background_command(command, timeout=timeout)

    async def close(self) -> None:
        if self._snapshot_task and not self._snapshot_task.done():
            self._snapshot_task.cancel()
            # @@@cross-loop-snapshot-close - Runtime.close may run on a different loop during manager cleanup.
            # Only await task cancellation when task belongs to the current running loop.
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            task_loop = self._snapshot_task.get_loop()
            if current_loop is task_loop:
                try:
                    await self._snapshot_task
                except asyncio.CancelledError:
                    pass
        self._snapshot_task = None
        await asyncio.to_thread(self._close_shell_sync)
