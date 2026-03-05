"""
Docker sandbox provider.

Implements SandboxProvider using local Docker containers.
"""

from __future__ import annotations

import asyncio
import shlex
import subprocess
import uuid
from collections.abc import Callable

from sandbox.interfaces.executor import ExecuteResult
from sandbox.provider import Metrics, ProviderCapability, ProviderExecResult, SandboxProvider, SessionInfo
from sandbox.runtime import (
    _RemoteRuntimeBase,
    _SubprocessPtySession,
    _extract_state_from_output,
    _parse_env_output,
)


class DockerProvider(SandboxProvider):
    """
    Local Docker sandbox provider.

    Notes:
    - Requires Docker CLI available on host.
    - Uses one container per session.
    - If context_id is provided, uses a named Docker volume for persistence.
    """

    name = "docker"

    def get_capability(self) -> ProviderCapability:
        return ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
            supports_webhook=False,
            runtime_kind="docker_pty",
        )

    def __init__(
        self,
        image: str,
        mount_path: str = "/workspace",
        command_timeout_sec: float = 20.0,
        provider_name: str | None = None,
    ):
        if provider_name:
            self.name = provider_name
        self.image = image
        self.mount_path = mount_path
        self.command_timeout_sec = command_timeout_sec
        self._sessions: dict[str, str] = {}  # session_id -> container_id

    def create_session(self, context_id: str | None = None) -> SessionInfo:
        session_id = f"leon-{uuid.uuid4().hex[:12]}"
        container_name = session_id

        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--label",
            f"leon.session_id={session_id}",
        ]

        if context_id:
            volume = context_id
            cmd.extend(["-v", f"{volume}:{self.mount_path}"])

        cmd.extend(["-w", self.mount_path, self.image, "sleep", "infinity"])

        result = self._run(cmd, timeout=self.command_timeout_sec)
        container_id = result.stdout.strip()
        if not container_id:
            raise RuntimeError("Failed to create docker container session")

        self._sessions[session_id] = container_id
        return SessionInfo(session_id=session_id, provider=self.name, status="running")

    def destroy_session(self, session_id: str, sync: bool = True) -> bool:
        container_id = self._get_container_id(session_id)
        result = self._run(["docker", "rm", "-f", container_id], timeout=self.command_timeout_sec, check=False)
        if result.returncode == 0:
            self._sessions.pop(session_id, None)
            return True
        return False

    def pause_session(self, session_id: str) -> bool:
        container_id = self._get_container_id(session_id)
        result = self._run(["docker", "pause", container_id], timeout=self.command_timeout_sec, check=False)
        return result.returncode == 0

    def resume_session(self, session_id: str) -> bool:
        container_id = self._get_container_id(session_id)
        result = self._run(["docker", "unpause", container_id], timeout=self.command_timeout_sec, check=False)
        return result.returncode == 0

    def get_session_status(self, session_id: str) -> str:
        container_id = self._get_container_id(session_id, allow_missing=True)
        if not container_id:
            return "deleted"
        try:
            result = self._run(
                ["docker", "inspect", "-f", "{{.State.Status}}", container_id],
                timeout=self.command_timeout_sec,
                check=False,
            )
        except RuntimeError:
            return "unknown"
        status = result.stdout.strip().lower()
        if status in {"running", "paused", "exited", "dead"}:
            return "paused" if status == "paused" else "running" if status == "running" else "deleted"
        return "unknown"

    def execute(
        self,
        session_id: str,
        command: str,
        timeout_ms: int = 30000,
        cwd: str | None = None,
    ) -> ProviderExecResult:
        container_id = self._get_container_id(session_id)
        workdir = cwd or self.mount_path
        shell_cmd = f"cd {shlex.quote(workdir)} && {command}"
        result = self._run(
            ["docker", "exec", container_id, "/bin/sh", "-lc", shell_cmd],
            timeout=max(timeout_ms / 1000, self.command_timeout_sec),
            check=False,
        )
        return ProviderExecResult(
            output=result.stdout,
            exit_code=result.returncode,
            error=result.stderr or None,
        )

    def read_file(self, session_id: str, path: str) -> str:
        container_id = self._get_container_id(session_id)
        result = self._run(
            ["docker", "exec", container_id, "cat", path],
            timeout=self.command_timeout_sec,
            check=False,
        )
        if result.returncode != 0:
            raise OSError(result.stderr.strip() or "Failed to read file")
        return result.stdout

    def write_file(self, session_id: str, path: str, content: str) -> str:
        container_id = self._get_container_id(session_id)
        cmd = ["docker", "exec", "-i", container_id, "/bin/sh", "-lc", f"cat > {shlex.quote(path)}"]
        result = self._run(cmd, input_text=content, timeout=self.command_timeout_sec, check=False)
        if result.returncode != 0:
            raise OSError(result.stderr.strip() or "Failed to write file")
        return f"Written: {path}"

    def list_dir(self, session_id: str, path: str) -> list[dict]:
        container_id = self._get_container_id(session_id)
        script = (
            f"cd {shlex.quote(path)} 2>/dev/null || exit 1; "
            "ls -A1 2>/dev/null | while IFS= read -r f; do "
            'if [ -d "$f" ]; then t=directory; else t=file; fi; '
            's=$(stat -c %s "$f" 2>/dev/null || wc -c <"$f" 2>/dev/null || echo 0); '
            'printf "%s\\t%s\\t%s\\n" "$t" "$s" "$f"; '
            "done"
        )
        result = self._run(
            ["docker", "exec", container_id, "/bin/sh", "-lc", script],
            timeout=self.command_timeout_sec,
            check=False,
        )
        if result.returncode != 0:
            return []
        items: list[dict] = []
        for line in result.stdout.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            item_type, size_str, name = parts
            try:
                size = int(size_str)
            except ValueError:
                size = 0
            items.append({"name": name, "type": item_type, "size": size})
        return items

    def upload(self, session_id: str, local_path: str, remote_path: str) -> str:
        container_id = self._get_container_id(session_id)
        result = self._run(
            ["docker", "cp", local_path, f"{container_id}:{remote_path}"],
            timeout=self.command_timeout_sec,
            check=False,
        )
        if result.returncode != 0:
            raise OSError(result.stderr.strip() or "Failed to upload file")
        return f"Uploaded: {local_path} -> {remote_path}"

    def download(self, session_id: str, remote_path: str, local_path: str) -> str:
        container_id = self._get_container_id(session_id)
        result = self._run(
            ["docker", "cp", f"{container_id}:{remote_path}", local_path],
            timeout=self.command_timeout_sec,
            check=False,
        )
        if result.returncode != 0:
            raise OSError(result.stderr.strip() or "Failed to download file")
        return f"Downloaded: {remote_path} -> {local_path}"

    def get_metrics(self, session_id: str) -> Metrics | None:
        container_id = self._get_container_id(session_id, allow_missing=True)
        if not container_id:
            return None
        result = self._run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}",
                container_id,
            ],
            timeout=self.command_timeout_sec,
            check=False,
        )
        if result.returncode != 0:
            return None
        parts = result.stdout.strip().split("\t")
        if len(parts) != 4:
            return None
        cpu_percent = self._parse_percent(parts[0])
        mem_used, mem_total = self._parse_mem_usage(parts[1])
        net_rx, net_tx = self._parse_io(parts[2])
        disk_used, disk_total = self._parse_io(parts[3])
        return Metrics(
            cpu_percent=cpu_percent,
            memory_used_mb=mem_used,
            memory_total_mb=mem_total,
            disk_used_gb=disk_used / 1024,
            disk_total_gb=disk_total / 1024,
            network_rx_kbps=net_rx,
            network_tx_kbps=net_tx,
        )

    def create_runtime(self, terminal, lease):
        return DockerPtyRuntime(terminal, lease, self)

    def _get_container_id(self, session_id: str, allow_missing: bool = False) -> str | None:
        container_id = self._sessions.get(session_id)
        if container_id:
            return container_id
        result = self._run(
            ["docker", "ps", "-aq", "--filter", f"label=leon.session_id={session_id}"],
            timeout=self.command_timeout_sec,
            check=False,
        )
        container_id = result.stdout.strip()
        if container_id:
            self._sessions[session_id] = container_id
            return container_id
        if allow_missing:
            return None
        raise RuntimeError(f"Docker session not found: {session_id}")

    def _run(
        self,
        cmd: list[str],
        *,
        timeout: float | None = None,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        effective_timeout = timeout if timeout is not None else self.command_timeout_sec
        try:
            result = subprocess.run(
                cmd,
                input=input_text,
                text=True,
                capture_output=True,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Docker command timed out after {effective_timeout}s: {' '.join(cmd)}") from exc
        if check and result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Docker command failed")
        return result

    def _parse_percent(self, value: str) -> float:
        value = value.strip().replace("%", "")
        try:
            return float(value)
        except ValueError:
            return 0.0

    def _parse_mem_usage(self, value: str) -> tuple[float, float]:
        parts = [p.strip() for p in value.split("/")]
        if len(parts) != 2:
            return 0.0, 0.0
        return self._parse_size_mb(parts[0]), self._parse_size_mb(parts[1])

    def _parse_io(self, value: str) -> tuple[float, float]:
        parts = [p.strip() for p in value.split("/")]
        if len(parts) != 2:
            return 0.0, 0.0
        return self._parse_size_kb(parts[0]), self._parse_size_kb(parts[1])

    def _parse_size_mb(self, value: str) -> float:
        num, unit = self._split_size(value)
        if unit == "b":
            return num / 1024 / 1024
        if unit == "kb":
            return num / 1024
        if unit == "mb":
            return num
        if unit == "gb":
            return num * 1024
        if unit == "tb":
            return num * 1024 * 1024
        return 0.0

    def _parse_size_kb(self, value: str) -> float:
        num, unit = self._split_size(value)
        if unit == "b":
            return num / 1024
        if unit == "kb":
            return num
        if unit == "mb":
            return num * 1024
        if unit == "gb":
            return num * 1024 * 1024
        if unit == "tb":
            return num * 1024 * 1024 * 1024
        return 0.0

    def _split_size(self, value: str) -> tuple[float, str]:
        value = value.strip()
        if not value:
            return 0.0, ""
        num = ""
        unit = ""
        for ch in value:
            if ch.isdigit() or ch == ".":
                num += ch
            else:
                unit += ch
        try:
            num_f = float(num) if num else 0.0
        except ValueError:
            num_f = 0.0
        unit = unit.strip().lower()
        if unit.endswith("ib"):
            unit = unit.replace("ib", "b")
        return num_f, unit


# ── Runtime ──────────────────────────────────────────────────────────────────


class DockerPtyRuntime(_RemoteRuntimeBase):
    """Docker runtime using a persistent PTY shell inside container."""

    def __init__(self, terminal, lease, provider):
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
