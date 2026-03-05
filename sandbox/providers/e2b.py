"""
E2B sandbox provider.

Implements SandboxProvider using E2B's cloud sandbox SDK.

Key differences from AgentBay:
- No persistent storage (context_id ignored) -- pause is the only way to preserve state
- Pause/resume via beta API: beta_pause() / Sandbox.connect()
- Uses beta_create(auto_pause=True) so sandboxes pause on timeout instead of dying
"""

from __future__ import annotations

import os
from typing import Any

from sandbox.provider import (
    Metrics,
    ProviderCapability,
    ProviderExecResult,
    SandboxProvider,
    SessionInfo,
)


class E2BProvider(SandboxProvider):
    """E2B cloud sandbox provider."""

    name = "e2b"
    WORKSPACE_ROOT = "/home/user/workspace"

    def get_capability(self) -> ProviderCapability:
        return ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
            supports_webhook=False,
            runtime_kind="e2b_pty",
        )

    def __init__(
        self,
        api_key: str,
        template: str = "base",
        default_cwd: str = "/home/user",
        timeout: int = 300,
        provider_name: str | None = None,
    ):
        if provider_name:
            self.name = provider_name
        self.api_key = api_key
        # @@@ E2B SDK methods like beta_pause() read from env, not from instance
        os.environ["E2B_API_KEY"] = api_key
        self.template = template
        self.default_cwd = default_cwd
        self.timeout = timeout
        self._sandboxes: dict[str, Any] = {}

    def create_session(self, context_id: str | None = None) -> SessionInfo:
        from e2b import Sandbox

        sandbox = Sandbox.beta_create(
            template=self.template,
            timeout=self.timeout,
            auto_pause=True,
            api_key=self.api_key,
        )
        self._sandboxes[sandbox.sandbox_id] = sandbox

        return SessionInfo(
            session_id=sandbox.sandbox_id,
            provider=self.name,
            status="running",
        )

    def destroy_session(self, session_id: str, sync: bool = True) -> bool:
        from e2b import Sandbox

        try:
            sandbox = self._sandboxes.pop(session_id, None)
            if sandbox:
                sandbox.kill()
            else:
                Sandbox.kill(session_id, api_key=self.api_key)
            return True
        except Exception:
            return False

    def pause_session(self, session_id: str) -> bool:
        try:
            sandbox = self._get_sandbox(session_id)
            sandbox.beta_pause()
            self._sandboxes.pop(session_id, None)
            return True
        except Exception:
            return False

    def resume_session(self, session_id: str) -> bool:
        from e2b import Sandbox

        try:
            sandbox = Sandbox.connect(
                session_id,
                timeout=self.timeout,
                api_key=self.api_key,
            )
            self._sandboxes[session_id] = sandbox
            return True
        except Exception:
            return False

    def get_session_status(self, session_id: str) -> str:
        from e2b import Sandbox

        try:
            # @@@ Sandbox.list() returns a paginator, not a list
            paginator = Sandbox.list(api_key=self.api_key)
            items = paginator.next_items()
            for s in items:
                if s.sandbox_id == session_id:
                    return s.state.value
            return "deleted"
        except Exception:
            return "unknown"

    def get_all_session_statuses(self) -> dict[str, str]:
        """Batch status check — one API call for all sessions."""
        from e2b import Sandbox

        try:
            paginator = Sandbox.list(api_key=self.api_key)
            items = paginator.next_items()
            return {s.sandbox_id: s.state.value for s in items}
        except Exception:
            return {}

    def execute(
        self,
        session_id: str,
        command: str,
        timeout_ms: int = 30000,
        cwd: str | None = None,
    ) -> ProviderExecResult:
        sandbox = self._get_sandbox(session_id)
        try:
            result = sandbox.commands.run(
                command,
                cwd=cwd or self.default_cwd,
                timeout=timeout_ms / 1000,
            )
            output = result.stdout or ""
            if result.stderr:
                output += f"\n{result.stderr}" if output else result.stderr

            return ProviderExecResult(
                output=output,
                exit_code=result.exit_code,
            )
        except Exception as e:
            return ProviderExecResult(output="", error=str(e))

    def read_file(self, session_id: str, path: str) -> str:
        sandbox = self._get_sandbox(session_id)
        return sandbox.files.read(path)

    def write_file(self, session_id: str, path: str, content: str) -> str:
        sandbox = self._get_sandbox(session_id)
        sandbox.files.write(path, content)
        return f"Written: {path}"

    def list_dir(self, session_id: str, path: str) -> list[dict]:
        sandbox = self._get_sandbox(session_id)
        try:
            entries = sandbox.files.list(path)
            return [
                {
                    "name": entry.name,
                    "type": "directory" if entry.type and entry.type.value == "dir" else "file",
                    "size": getattr(entry, "size", 0) or 0,
                }
                for entry in entries
            ]
        except Exception:
            return []

    def get_metrics(self, session_id: str) -> Metrics | None:
        return None

    def snapshot_workspace(self, session_id: str) -> list[dict]:
        """Download all files from /home/user/workspace."""
        sandbox = self._get_sandbox(session_id)
        stack = [self.WORKSPACE_ROOT]
        files = []
        while stack:
            d = stack.pop()
            try:
                entries = sandbox.files.list(d)
            except Exception:
                continue
            for entry in entries:
                p = entry.path if hasattr(entry, "path") else f"{d}/{entry.name}"
                if entry.type and entry.type.value == "dir":
                    stack.append(p)
                    continue
                try:
                    data = sandbox.files.read(p, format="bytes")
                    rel = p.removeprefix(self.WORKSPACE_ROOT + "/")
                    files.append({"file_path": rel, "content": bytes(data)})
                except Exception:
                    continue
        return files

    def restore_workspace(self, session_id: str, files: list[dict]) -> None:
        """Upload files back into /home/user/workspace."""
        sandbox = self._get_sandbox(session_id)
        for f in files:
            abs_path = f"{self.WORKSPACE_ROOT}/{f['file_path']}"
            sandbox.files.write(abs_path, f["content"])

    def _get_sandbox(self, session_id: str):
        """Get sandbox object, reconnecting if not cached."""
        if session_id not in self._sandboxes:
            from e2b import Sandbox

            sandbox = Sandbox.connect(
                session_id,
                timeout=self.timeout,
                api_key=self.api_key,
            )
            self._sandboxes[session_id] = sandbox
        return self._sandboxes[session_id]

    def get_runtime_sandbox(self, session_id: str):
        """Expose native SDK sandbox for runtime-level persistent terminal handling."""
        return self._get_sandbox(session_id)

    def create_runtime(self, terminal, lease):
        from sandbox.providers.e2b import E2BPtyRuntime
        return E2BPtyRuntime(terminal, lease, self)


# ── Runtime ──────────────────────────────────────────────────────────────────

import asyncio  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402

from sandbox.interfaces.executor import ExecuteResult  # noqa: E402
from sandbox.runtime import (  # noqa: E402
    _RemoteRuntimeBase,
    _extract_state_from_output,
    _normalize_pty_result,
    _parse_env_output,
    _sanitize_shell_output,
)


class E2BPtyRuntime(_RemoteRuntimeBase):
    """E2B runtime using native SDK PTY handle for persistent shell."""

    def __init__(self, terminal, lease, provider):
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
