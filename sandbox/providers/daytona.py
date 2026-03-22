"""
Daytona sandbox provider.

Uses Daytona's Python SDK for sandbox lifecycle, filesystem, and process execution.

Important: runtime semantics remain PTY-backed (`daytona_pty`) for both SaaS and self-hosted.
"""

from __future__ import annotations

import logging
import os
import shlex
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from sandbox.config import MountSpec
from sandbox.provider import (
    Metrics,
    MountCapability,
    ProviderCapability,
    ProviderExecResult,
    SandboxProvider,
    SessionInfo,
    build_resource_capabilities,
)


def _daytona_state_to_status(state: str) -> str:
    if state == "started":
        return "running"
    if state == "stopped":
        return "paused"
    return "unknown"

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sandbox.lease import SandboxLease
    from sandbox.runtime import PhysicalTerminalRuntime
    from sandbox.terminal import AbstractTerminal


class DaytonaProvider(SandboxProvider):
    """Daytona cloud sandbox provider."""

    CATALOG_ENTRY = {"vendor": "Daytona", "description": "Managed cloud or self-host Daytona sandboxes", "provider_type": "cloud"}

    name = "daytona"
    CAPABILITY = ProviderCapability(
        can_pause=True,
        can_resume=True,
        can_destroy=True,
        supports_webhook=True,
        runtime_kind="daytona_pty",
        resource_capabilities=build_resource_capabilities(
            filesystem=True,
            terminal=True,
            metrics=True,
            screenshot=False,
            web=False,
            process=False,
            hooks=True,
            mount=True,
        ),
        mount=MountCapability(
            supports_mount=True,
            supports_copy=True,
            supports_read_only=True,
            mode_handlers={"mount": True, "copy": True},
            supports_workplace=True,
        ),
    )
    WORKSPACE_ROOT = "/home/daytona"

    def get_capability(self) -> ProviderCapability:
        return self.CAPABILITY

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://app.daytona.io/api",
        target: str = "local",
        default_cwd: str = "/home/daytona",
        bind_mounts: list[MountSpec] | None = None,
        provider_name: str | None = None,
    ):
        from daytona_sdk import Daytona

        if provider_name:
            self.name = provider_name
        self.api_key = api_key
        self.api_url = api_url
        self.target = target
        self.default_cwd = default_cwd
        self.bind_mounts: list[MountSpec] = [
            MountSpec.model_validate(m) if isinstance(m, dict) else m for m in (bind_mounts or [])
        ]

        os.environ["DAYTONA_API_KEY"] = api_key
        os.environ["DAYTONA_API_URL"] = api_url
        self.client = Daytona()
        self._sandboxes: dict[str, Any] = {}
        self._thread_bind_mounts: dict[str, list[MountSpec]] = {}  # thread_id -> bind_mounts
        self._workplace_mounts: dict[str, tuple[str, str]] = {}  # thread_id -> (volume_id, mount_path)

    def set_thread_bind_mounts(self, thread_id: str, mounts: list[MountSpec | dict]) -> None:
        """Set thread-specific bind mounts that will be applied when creating sessions."""
        self._thread_bind_mounts[thread_id] = [
            MountSpec.model_validate(m) if isinstance(m, dict) else m for m in mounts
        ]

    # ==================== Workplace ====================

    def create_workplace(self, member_id: str, mount_path: str) -> str:
        """Create a Daytona volume for the agent. Returns volume name as backend_ref."""
        volume_name = f"leon-workplace-{member_id}"
        logger.info("Creating workplace volume: %s", volume_name)
        # @@@workplace-volume-ready - volume transitions pending_create → ready (~6s)
        self.client.volume.create(volume_name)
        for _ in range(30):
            vol = self.client.volume.get(volume_name)
            if vol.state == "ready":
                logger.info("Workplace volume ready: %s (id=%s)", volume_name, vol.id)
                return volume_name
            time.sleep(1)
        raise RuntimeError(f"Volume {volume_name} did not become ready within 30s")

    def set_workplace_mount(self, thread_id: str, backend_ref: str, mount_path: str) -> None:
        self._workplace_mounts[thread_id] = (backend_ref, mount_path)

    def delete_workplace(self, backend_ref: str) -> None:
        """Delete workplace volume. backend_ref is the volume name."""
        logger.info("Deleting workplace volume: %s", backend_ref)
        vol = self.client.volume.get(backend_ref)
        self.client.volume.delete(vol)

    # ==================== Session Lifecycle ====================

    def create_session(self, context_id: str | None = None, thread_id: str | None = None) -> SessionInfo:
        from daytona_sdk import CreateSandboxFromSnapshotParams, VolumeMount

        # @@@workplace-volume-mount - use SDK VolumeMount instead of bind mount HTTP workaround
        if thread_id and thread_id in self._workplace_mounts:
            volume_name, wp_mount_path = self._workplace_mounts.pop(thread_id)
            vol = self.client.volume.get(volume_name)
            params = CreateSandboxFromSnapshotParams(
                target=self.target,
                auto_stop_interval=0,
                volumes=[VolumeMount(volume_id=vol.id, mount_path=wp_mount_path)],
            )
            sb = self.client.create(params)
            # @@@workplace-chown - Docker-in-Docker bind mount loses FUSE uid/gid
            sb.process.exec(f"sudo chown daytona:daytona {wp_mount_path}", timeout=10)
            self._sandboxes[sb.id] = sb
            return SessionInfo(session_id=sb.id, provider=self.name, status="running")

        # Merge global bind_mounts with thread-specific mounts
        all_mounts = list(self.bind_mounts)
        if thread_id and thread_id in self._thread_bind_mounts:
            all_mounts.extend(self._thread_bind_mounts[thread_id])

        mount_mounts: list[MountSpec] = []
        copy_mounts: list[tuple[str, str]] = []
        for mount in all_mounts:
            if mount.mode == "copy":
                copy_mounts.append((mount.source, mount.target))
            else:
                mount_mounts.append(mount)

        if mount_mounts:
            # @@@daytona-bindmount-http-create - SDK currently lacks bind_mounts field, so self-host bind mounts use direct API create.
            sandbox_id = self._create_via_http(bind_mounts=mount_mounts)
            self._wait_until_started(sandbox_id)
            sb = self.client.find_one(sandbox_id)
        else:
            params = CreateSandboxFromSnapshotParams(target=self.target, auto_stop_interval=0)
            sb = self.client.create(params)

        for source, target in copy_mounts:
            self._copy_host_path_into_sandbox(sb, source=source, target=target)

        self._sandboxes[sb.id] = sb
        return SessionInfo(session_id=sb.id, provider=self.name, status="running")

    def destroy_session(self, session_id: str, sync: bool = True) -> bool:
        try:
            sb = self._get_sandbox(session_id)
            sb.delete()
            self._sandboxes.pop(session_id, None)
            return True
        except Exception:
            # @@@destroy-verify-actual - verify sandbox is truly gone before reporting failure
            logger.warning("[DaytonaProvider] destroy_session error for %s, verifying actual state", session_id)
            actual = self.get_session_status(session_id)
            if actual == "unknown":
                # Sandbox no longer findable — delete succeeded
                logger.info("[DaytonaProvider] sandbox %s no longer exists — destroy succeeded", session_id)
                self._sandboxes.pop(session_id, None)
                return True
            logger.error("[DaytonaProvider] destroy_session truly failed for %s (state=%s)", session_id, actual)
            return False

    def pause_session(self, session_id: str) -> bool:
        try:
            sb = self._get_sandbox(session_id)
            sb.stop()
            return True
        except Exception:
            # @@@pause-verify-actual - sb.stop() can throw (e.g. Daytona 502 during wait)
            # even though the sandbox actually stopped. Verify real state before giving up.
            logger.warning("[DaytonaProvider] pause_session error for %s, verifying actual state", session_id)
            actual = self.get_session_status(session_id)
            if actual == "paused":
                logger.info("[DaytonaProvider] sandbox %s is actually stopped despite error — pause succeeded", session_id)
                return True
            logger.error("[DaytonaProvider] pause_session truly failed for %s (state=%s)", session_id, actual)
            return False

    def resume_session(self, session_id: str) -> bool:
        try:
            sb = self._get_sandbox(session_id)
            sb.start()
            return True
        except Exception:
            # @@@resume-verify-actual - same pattern as pause: verify real state on error
            logger.warning("[DaytonaProvider] resume_session error for %s, verifying actual state", session_id)
            actual = self.get_session_status(session_id)
            if actual == "running":
                logger.info("[DaytonaProvider] sandbox %s is actually running despite error — resume succeeded", session_id)
                return True
            logger.error("[DaytonaProvider] resume_session truly failed for %s (state=%s)", session_id, actual)
            return False

    def get_session_status(self, session_id: str) -> str:
        try:
            # @@@status-refresh - Always refetch sandbox before reading state to avoid stale cached status.
            sb = self.client.find_one(session_id)
            self._sandboxes[session_id] = sb
            return _daytona_state_to_status(sb.state.value)
        except Exception:
            logger.exception("[DaytonaProvider] get_session_status failed for %s", session_id)
            return "unknown"

    # ==================== Execution ====================

    def execute(
        self,
        session_id: str,
        command: str,
        timeout_ms: int = 30000,
        cwd: str | None = None,
    ) -> ProviderExecResult:
        sb = self._get_sandbox(session_id)
        result = sb.process.exec(command, cwd=cwd or self.default_cwd, timeout=timeout_ms // 1000)
        return ProviderExecResult(output=result.result or "", exit_code=int(result.exit_code or 0))

    # ==================== Filesystem ====================

    def read_file(self, session_id: str, path: str) -> str:
        sb = self._get_sandbox(session_id)
        # @@@ download_file returns bytes, not str
        content = sb.fs.download_file(path)
        if isinstance(content, bytes):
            return content.decode("utf-8")
        return content or ""

    def write_file(self, session_id: str, path: str, content: str) -> str:
        sb = self._get_sandbox(session_id)
        sb.fs.upload_file(content.encode("utf-8"), path)
        return f"Written: {path}"

    def list_dir(self, session_id: str, path: str) -> list[dict]:
        sb = self._get_sandbox(session_id)
        entries = sb.fs.list_files(path)
        return [
            {"name": e.name, "type": "directory" if e.is_dir else "file", "size": e.size or 0} for e in (entries or [])
        ]

    # ==================== Batch Status ====================

    def list_provider_sessions(self) -> list[SessionInfo]:
        result = self.client.list()
        return [
            SessionInfo(session_id=sb.id, provider=self.name, status=_daytona_state_to_status(sb.state.value))
            for sb in result.items
        ]

    # ==================== Inspection ====================

    def get_metrics(self, session_id: str) -> Metrics | None:
        # @@@daytona-metrics - SDK gives static limits (memory/disk quota).
        # For running sandboxes: one composite cgroup v2 command collects live CPU + memory (~237ms).
        # free/top are NOT installed in Daytona containers; df / shows host disk (useless per-container).
        # memory.max='max' (no cgroup limit) → memory_total from SDK quota only.
        try:
            sb = self.client.find_one(session_id)
            self._sandboxes[session_id] = sb
        except Exception:
            return None

        memory_gib = getattr(sb, "memory", None)
        disk_gib = getattr(sb, "disk", None)
        memory_total_mb = float(memory_gib) * 1024.0 if memory_gib else None
        disk_total_gb = float(disk_gib) if disk_gib else None

        is_running = getattr(sb, "state", None) and sb.state.value == "started"
        if not is_running:
            return Metrics(memory_total_mb=memory_total_mb, disk_total_gb=disk_total_gb)

        # Two-sample cpu.stat (0.2s window) + memory.current + du workspace in one execute() call.
        # Separator lets us split the output cleanly without fragile line-counting.
        # @@@daytona-disk - df / shows HOST disk (not container quota); use du for workspace usage only.
        cmd = (
            "cat /sys/fs/cgroup/cpu.stat"
            "; sleep 0.2"
            "; echo '---MEM---'"
            "; cat /sys/fs/cgroup/memory.current"
            "; echo '---CPU2---'"
            "; cat /sys/fs/cgroup/cpu.stat"
            "; echo '---DISK---'"
            "; du -sm /home/daytona 2>/dev/null || echo 0"
        )
        result = self.execute(session_id, cmd, timeout_ms=5000)

        cpu_percent = None
        memory_used_mb = None
        disk_used_gb = None

        if result.exit_code == 0 and result.output:
            try:
                mem_marker = "---MEM---"
                cpu2_marker = "---CPU2---"
                disk_marker = "---DISK---"
                text = result.output
                i_mem = text.index(mem_marker)
                i_cpu2 = text.index(cpu2_marker)
                i_disk = text.index(disk_marker)

                cpu1_block = text[:i_mem]
                mem_block = text[i_mem + len(mem_marker):i_cpu2]
                cpu2_block = text[i_cpu2 + len(cpu2_marker):i_disk]
                disk_block = text[i_disk + len(disk_marker):]

                def _usage_usec(block: str) -> int | None:
                    for line in block.splitlines():
                        if line.startswith("usage_usec"):
                            return int(line.split()[1])
                    return None

                u1 = _usage_usec(cpu1_block)
                u2 = _usage_usec(cpu2_block)
                if u1 is not None and u2 is not None:
                    # delta_usec / 200_000us (0.2s window) * 100 → CPU%
                    cpu_percent = (u2 - u1) / 2_000.0

                mem_str = mem_block.strip()
                if mem_str.isdigit():
                    memory_used_mb = int(mem_str) / (1024 ** 2)

                # du -sm outputs "<MB>\t<path>"; parse the first token
                disk_line = disk_block.strip().splitlines()[0] if disk_block.strip() else ""
                disk_mb_str = disk_line.split()[0] if disk_line else ""
                if disk_mb_str.isdigit() and int(disk_mb_str) > 0:
                    disk_used_gb = int(disk_mb_str) / 1024.0
            except Exception:
                pass

        return Metrics(
            cpu_percent=cpu_percent,
            memory_used_mb=memory_used_mb,
            memory_total_mb=memory_total_mb,
            disk_used_gb=disk_used_gb,
            disk_total_gb=disk_total_gb,
        )

    # ==================== Internal ====================

    def _get_sandbox(self, session_id: str):
        if session_id not in self._sandboxes:
            self._sandboxes[session_id] = self.client.find_one(session_id)
        return self._sandboxes[session_id]

    def get_runtime_sandbox(self, session_id: str):
        """Expose native SDK sandbox for runtime-level persistent terminal handling."""
        return self._get_sandbox(session_id)

    def _api_auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _create_via_http(self, bind_mounts: list[MountSpec]) -> str:
        normalized_mounts: list[dict[str, Any]] = []
        for mount in bind_mounts:
            if mount.mode != "mount":
                continue
            normalized_mounts.append({"hostPath": mount.source, "mountPath": mount.target, "readOnly": mount.read_only})
        payload = {
            "name": f"leon-{uuid.uuid4().hex[:12]}",
            "autoStopInterval": 0,
            "bindMounts": normalized_mounts,
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{self.api_url.rstrip('/')}/sandbox", headers=self._api_auth_headers(), json=payload)
        if response.status_code != 200:
            raise RuntimeError(f"Daytona create sandbox failed ({response.status_code}): {response.text}")
        sandbox_id = response.json().get("id")
        if not sandbox_id:
            raise RuntimeError(f"Daytona create sandbox response missing id: {response.text}")
        return str(sandbox_id)

    def _copy_host_path_into_sandbox(self, sb: Any, *, source: str, target: str) -> None:
        source_path = Path(source)
        if not source_path.exists():
            raise RuntimeError(f"Copy source path does not exist: {source}")

        self._mkdir_in_sandbox(sb, target if source_path.is_dir() else str(Path(target).parent))

        if source_path.is_file():
            sb.fs.upload_file(source_path.read_bytes(), target)
            return
        if source_path.is_dir():
            for local_path in source_path.rglob("*"):
                if local_path.is_dir():
                    rel_dir = local_path.relative_to(source_path)
                    self._mkdir_in_sandbox(sb, str(Path(target) / rel_dir))
                    continue
                if local_path.is_file():
                    remote_file = str(Path(target) / local_path.relative_to(source_path))
                    self._mkdir_in_sandbox(sb, str(Path(remote_file).parent))
                    sb.fs.upload_file(local_path.read_bytes(), remote_file)
                    continue
                raise RuntimeError(f"Unsupported copy source path type: {local_path}")
            return
        raise RuntimeError(f"Unsupported copy source path type: {source}")

    def _mkdir_in_sandbox(self, sb: Any, path: str) -> None:
        quoted = shlex.quote(path)
        result = sb.process.exec(f"mkdir -p {quoted}", cwd=self.default_cwd, timeout=30)
        if int(result.exit_code or 0) != 0:
            raise RuntimeError(f"Failed to create directory in sandbox: {path}; stderr={result.result!r}")

    def _wait_until_started(self, sandbox_id: str, timeout_seconds: int = 120) -> None:
        deadline = time.time() + timeout_seconds
        with httpx.Client(timeout=15.0) as client:
            while time.time() < deadline:
                response = client.get(f"{self.api_url.rstrip('/')}/sandbox/{sandbox_id}", headers=self._api_auth_headers())
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Daytona get sandbox failed while waiting for started ({response.status_code}): {response.text}"
                    )
                body = response.json()
                state = str(body.get("state") or "")
                if state == "started":
                    return
                if state in {"destroyed", "destroying", "error", "failed"}:
                    raise RuntimeError(f"Daytona sandbox entered bad state '{state}': {response.text}")
                time.sleep(2)
        raise RuntimeError(f"Timed out waiting for Daytona sandbox {sandbox_id} to reach started state")

    def create_runtime(self, terminal: AbstractTerminal, lease: SandboxLease) -> PhysicalTerminalRuntime:
        from sandbox.providers.daytona import DaytonaSessionRuntime
        return DaytonaSessionRuntime(terminal, lease, self)


# ── Runtime ──────────────────────────────────────────────────────────────────

import asyncio  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shlex  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from collections.abc import Callable  # noqa: E402

from sandbox.interfaces.executor import ExecuteResult  # noqa: E402
from sandbox.runtime import (  # noqa: E402
    ENV_NAME_RE,
    _RemoteRuntimeBase,
    _SubprocessPtySession,
    _build_export_block,
    _build_state_snapshot_cmd,
    _compute_env_delta,
    _extract_marker_exit,
    _extract_state_from_output,
    _parse_env_output,
    _sanitize_shell_output,
)


class DaytonaSessionRuntime(_RemoteRuntimeBase):
    """Daytona runtime using native PTY session API (persistent terminal semantics)."""

    def __init__(self, terminal, lease, provider):
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
                cleaned, exit_code = _extract_marker_exit(decoded, marker, command)
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
                    # @@@pty-fork-exec-error - "fork/exec /path: no such file" can mean shell OR cwd missing
                    if "fork/exec" in message and "no such file" in message:
                        # Diagnose: check if working directory exists
                        try:
                            result = sandbox.process.exec_sync(f"test -d {effective_cwd} && echo y || echo n", timeout=5)
                            if "n" in result.stdout:
                                raise RuntimeError(
                                    f"PTY bootstrap failed: working directory '{effective_cwd}' does not exist. "
                                    f"Update config 'cwd' to an existing directory (e.g., /home/daytona)."
                                ) from create_exc
                        except RuntimeError:
                            raise
                        except Exception:
                            pass  # Can't diagnose, fall through to shell check
                    if "/usr/bin/zsh" in message:
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
            export_block = _build_export_block(effective_env)
            init_command = "\n".join(p for p in [f"cd {shlex.quote(effective_cwd)} || exit 1", export_block] if p)
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
        start_marker, end_marker, snapshot_cmd = _build_state_snapshot_cmd()
        snapshot_out, _, _ = self._run_pty_command_sync(handle, snapshot_cmd, timeout)
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
