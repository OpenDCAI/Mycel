"""
Docker sandbox provider.

Implements SandboxProvider using local Docker containers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from sandbox.config import MountSpec
from sandbox.interfaces.executor import ExecuteResult
from sandbox.provider import (
    Metrics,
    MountCapability,
    ProviderCapability,
    ProviderExecResult,
    SandboxProvider,
    SessionInfo,
    build_resource_capabilities,
)
from sandbox.runtime import (
    _RemoteRuntimeBase,
    _SubprocessPtySession,
    _build_export_block,
    _build_state_snapshot_cmd,
    _compute_env_delta,
    _extract_state_from_output,
    _parse_env_output,
)

if TYPE_CHECKING:
    from sandbox.lease import SandboxLease
    from sandbox.runtime import PhysicalTerminalRuntime
    from sandbox.terminal import AbstractTerminal


class DockerProvider(SandboxProvider):
    """
    Local Docker sandbox provider.

    Notes:
    - Requires Docker CLI available on host.
    - Uses one container per session.
    - If context_id is provided, uses a named Docker volume for persistence.
    """

    CATALOG_ENTRY = {"vendor": None, "description": "Isolated container sandbox", "provider_type": "container"}

    name = "docker"
    CAPABILITY = ProviderCapability(
        can_pause=True,
        can_resume=True,
        can_destroy=True,
        supports_webhook=False,
        runtime_kind="docker_pty",
        resource_capabilities=build_resource_capabilities(
            filesystem=True,
            terminal=True,
            metrics=True,
            screenshot=False,
            web=False,
            process=False,
            hooks=False,
            mount=True,
        ),
        mount=MountCapability(
            supports_mount=True,
            supports_copy=True,
            supports_read_only=True,
            mode_handlers={"mount": True, "copy": True},
            supports_managed_volume=True,
        ),
    )

    def get_capability(self) -> ProviderCapability:
        return self.CAPABILITY

    def __init__(
        self,
        image: str,
        mount_path: str = "/workspace",
        default_cwd: str = "/workspace",
        bind_mounts: list[MountSpec] | None = None,
        command_timeout_sec: float = 20.0,
        provider_name: str | None = None,
        docker_host: str | None = None,
    ):
        if provider_name:
            self.name = provider_name
        self.image = image
        self.mount_path = mount_path
        self.default_cwd = default_cwd
        self.bind_mounts: list[MountSpec] = [
            MountSpec.model_validate(m) if isinstance(m, dict) else m for m in (bind_mounts or [])
        ]
        self.command_timeout_sec = command_timeout_sec
        self._docker_host = docker_host
        self._sessions: dict[str, str] = {}  # session_id -> container_id
        self._thread_bind_mounts: dict[str, list[MountSpec]] = {}  # thread_id -> bind_mounts
        self._volume_mounts: dict[str, MountSpec] = {}  # thread_id -> member volume bind mount

    def set_thread_bind_mounts(self, thread_id: str, mounts: list[MountSpec | dict]) -> None:
        """Set thread-specific bind mounts that will be applied when creating sessions."""
        self._thread_bind_mounts[thread_id] = [
            MountSpec.model_validate(m) if isinstance(m, dict) else m for m in mounts
        ]

    # ==================== Managed Volume ====================

    def create_managed_volume(self, member_id: str, mount_path: str) -> str:
        """Create a host directory as managed volume. Returns host path as backend_ref."""
        volume_dir = Path.home() / ".leon" / "managed_volumes" / member_id
        volume_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Created Docker managed volume: %s", volume_dir)
        return str(volume_dir)

    def set_managed_volume_mount(self, thread_id: str, backend_ref: str, mount_path: str) -> None:
        self._volume_mounts[thread_id] = MountSpec(
            source=backend_ref, target=mount_path, mode="mount", read_only=False,
        )

    def delete_managed_volume(self, backend_ref: str) -> None:
        """Delete managed volume host directory. backend_ref is the host path."""
        import shutil
        volume_dir = Path(backend_ref).resolve()
        # @@@safe-volume-delete - refuse to delete outside expected directory
        expected_parent = (Path.home() / ".leon" / "managed_volumes").resolve()
        if not str(volume_dir).startswith(str(expected_parent)):
            raise ValueError(f"Refusing to delete volume outside {expected_parent}: {volume_dir}")
        if volume_dir.exists():
            logger.info("Deleting Docker managed volume: %s", volume_dir)
            shutil.rmtree(volume_dir)

    def create_session(self, context_id: str | None = None, thread_id: str | None = None) -> SessionInfo:
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

        # Merge global bind_mounts with thread-specific mounts + member volume mount
        all_mounts = list(self.bind_mounts)
        if thread_id and thread_id in self._volume_mounts:
            all_mounts.append(self._volume_mounts.pop(thread_id))
        if thread_id and thread_id in self._thread_bind_mounts:
            all_mounts.extend(self._thread_bind_mounts[thread_id])

        copy_mounts: list[tuple[str, str]] = []
        for mount in all_mounts:
            if mount.mode == "copy":
                copy_mounts.append((mount.source, mount.target))
                continue
            volume_arg = f"{mount.source}:{mount.target}"
            if mount.read_only:
                volume_arg = f"{volume_arg}:ro"
            cmd.extend(["-v", volume_arg])

        if context_id:
            # @@@context-label - also label with context_id so probe can find container via lease_id
            cmd.extend(["--label", f"leon.context_id={context_id}"])
            volume = context_id
            cmd.extend(["-v", f"{volume}:{self.mount_path}"])

        cmd.extend(["-w", self.default_cwd, self.image, "sleep", "infinity"])

        result = self._run(cmd, timeout=self.command_timeout_sec)
        container_id = result.stdout.strip()
        if not container_id:
            raise RuntimeError("Failed to create docker container session")

        for source, target in copy_mounts:
            self._copy_host_path_into_container(container_id, source=source, target=target)

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
        workdir = cwd or self.default_cwd
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

        # Check state — docker stats only works on running containers.
        state_result = self._run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_id],
            timeout=self.command_timeout_sec,
            check=False,
        )
        if state_result.returncode != 0:
            return None
        container_state = state_result.stdout.strip()

        # @@@docker-paused-disk - paused/stopped containers still hold filesystem space.
        # docker stats won't work for them, but docker ps --size reads the writable layer without
        # touching the container process.
        if container_state != "running":
            return Metrics(
                cpu_percent=None,
                memory_used_mb=None,
                memory_total_mb=None,
                disk_used_gb=self._disk_usage_from_ps(container_id),
                disk_total_gb=None,
            )

        # CPU and memory RSS from docker stats.
        # @@@docker-memory-limit - no --memory flag set → MemUsage denominator is host RAM, not a container limit.
        stats_result = self._run(
            ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}\t{{.MemUsage}}", container_id],
            timeout=self.command_timeout_sec,
            check=False,
        )
        if stats_result.returncode != 0:
            return None
        parts = stats_result.stdout.strip().split("\t")
        if len(parts) != 2:
            return None
        cpu_percent = self._parse_percent(parts[0])
        mem_used, _ = self._parse_mem_usage(parts[1])  # ignore denominator (host RAM)

        # @@@docker-disk - BlockIO from docker stats is cumulative r/w bytes, not filesystem capacity.
        # Use df inside container for real disk usage.
        disk_result = self._run(
            ["docker", "exec", container_id, "df", "-BG", "/"],
            timeout=self.command_timeout_sec,
            check=False,
        )
        disk_used_gb = None
        if disk_result.returncode == 0:
            lines = disk_result.stdout.strip().splitlines()
            if len(lines) >= 2:
                df_parts = lines[1].split()
                if len(df_parts) >= 3:
                    try:
                        disk_used_gb = float(df_parts[2].rstrip("G"))
                    except ValueError:
                        pass

        return Metrics(
            cpu_percent=cpu_percent,
            memory_used_mb=mem_used,
            memory_total_mb=None,  # no --memory limit → no meaningful total
            disk_used_gb=disk_used_gb,
            disk_total_gb=None,  # @@@docker-disk-no-limit - no --storage-opt, df / total = host disk
        )

    def _disk_usage_from_ps(self, container_id: str) -> float | None:
        """Read writable-layer size for any container state via docker ps --size."""
        result = self._run(
            ["docker", "ps", "-a", "--filter", f"id={container_id}", "--format", "{{.Size}}"],
            timeout=self.command_timeout_sec,
            check=False,
        )
        if result.returncode != 0:
            return None
        size_str = result.stdout.strip()
        if not size_str:
            return None
        # Output: "8.19kB (virtual 159MB)" — first token is writable layer
        writable = size_str.split(" (")[0]
        try:
            if writable.endswith("GB"):
                return float(writable[:-2])
            if writable.endswith("MB"):
                return float(writable[:-2]) / 1024.0
            if writable.lower().endswith("kb"):
                return float(writable[:-2]) / (1024.0 * 1024.0)
            if writable.endswith("B"):
                return float(writable[:-1]) / (1024.0 ** 3)
        except ValueError:
            pass
        return None

    def _copy_host_path_into_container(self, container_id: str, *, source: str, target: str) -> None:
        source_path = Path(source)
        if not source_path.exists():
            raise RuntimeError(f"Copy source path does not exist: {source}")
        if source_path.is_dir():
            self._run(
                ["docker", "exec", container_id, "/bin/sh", "-lc", f"mkdir -p {shlex.quote(target)}"],
                timeout=self.command_timeout_sec,
            )
            self._run(
                ["docker", "cp", f"{source_path}/.", f"{container_id}:{target}"],
                timeout=self.command_timeout_sec,
            )
            return
        if source_path.is_file():
            parent = str(Path(target).parent)
            self._run(
                ["docker", "exec", container_id, "/bin/sh", "-lc", f"mkdir -p {shlex.quote(parent)}"],
                timeout=self.command_timeout_sec,
            )
            self._run(
                ["docker", "cp", str(source_path), f"{container_id}:{target}"],
                timeout=self.command_timeout_sec,
            )
            return
        raise RuntimeError(f"Unsupported copy source path type: {source}")

    def create_runtime(self, terminal: AbstractTerminal, lease: SandboxLease) -> PhysicalTerminalRuntime:
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

    # @@@proxy-isolation - docker CLI hangs when it inherits http_proxy/all_proxy from parent
    _PROXY_VARS = ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")

    def _run(
        self,
        cmd: list[str],
        *,
        timeout: float | None = None,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        effective_timeout = timeout if timeout is not None else self.command_timeout_sec
        # @@@proxy-isolation - strip proxy vars so Docker CLI uses unix socket directly
        env = {k: v for k, v in os.environ.items() if k not in self._PROXY_VARS}
        # @@@docker-host - pass DOCKER_HOST when configured to bypass stuck Docker Desktop context
        if self._docker_host:
            env["DOCKER_HOST"] = self._docker_host
        try:
            result = subprocess.run(
                cmd,
                input=input_text,
                text=True,
                capture_output=True,
                timeout=effective_timeout,
                env=env,
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
            exports = _build_export_block(state.env_delta)
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

        start_marker, end_marker, snapshot_cmd = _build_state_snapshot_cmd()
        snapshot_out, _, _ = session.run(snapshot_cmd, timeout)
        new_cwd, env_map, _ = _extract_state_from_output(
            snapshot_out,
            start_marker,
            end_marker,
            cwd_fallback=state.cwd,
            env_fallback=state.env_delta,
        )
        env_delta = _compute_env_delta(env_map, self._baseline_env or {}, state.env_delta)
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
