"""
Daytona sandbox provider.

Uses Daytona's Python SDK for sandbox lifecycle, filesystem, and process execution.

Important: runtime semantics remain PTY-backed (`daytona_pty`) for both SaaS and self-hosted.
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
    build_resource_capabilities,
)


class DaytonaProvider(SandboxProvider):
    """Daytona cloud sandbox provider."""

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
            snapshot=False,
        ),
    )

    def get_capability(self) -> ProviderCapability:
        return self.CAPABILITY

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://app.daytona.io/api",
        target: str = "local",
        default_cwd: str = "/home/daytona",
        provider_name: str | None = None,
    ):
        from daytona_sdk import Daytona

        if provider_name:
            self.name = provider_name
        self.api_key = api_key
        self.api_url = api_url
        self.target = target
        self.default_cwd = default_cwd

        os.environ["DAYTONA_API_KEY"] = api_key
        os.environ["DAYTONA_API_URL"] = api_url
        self.client = Daytona()
        self._sandboxes: dict[str, Any] = {}

    # ==================== Session Lifecycle ====================

    def create_session(self, context_id: str | None = None) -> SessionInfo:
        from daytona_sdk import CreateSandboxFromSnapshotParams

        params = CreateSandboxFromSnapshotParams(auto_stop_interval=0)
        sb = self.client.create(params)
        self._sandboxes[sb.id] = sb
        return SessionInfo(session_id=sb.id, provider=self.name, status="running")

    def destroy_session(self, session_id: str, sync: bool = True) -> bool:
        sb = self._get_sandbox(session_id)
        sb.delete()
        self._sandboxes.pop(session_id, None)
        return True

    def pause_session(self, session_id: str) -> bool:
        sb = self._get_sandbox(session_id)
        sb.stop()
        return True

    def resume_session(self, session_id: str) -> bool:
        sb = self._get_sandbox(session_id)
        sb.start()
        return True

    def get_session_status(self, session_id: str) -> str:
        # @@@status-refresh - Always refetch sandbox before reading state to avoid stale cached status.
        sb = self.client.find_one(session_id)
        self._sandboxes[session_id] = sb
        state = sb.state.value
        if state == "started":
            return "running"
        if state == "stopped":
            return "paused"
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
        try:
            result = sb.process.exec(command, cwd=cwd or self.default_cwd, timeout=timeout_ms // 1000)
            return ProviderExecResult(output=result.result or "", exit_code=int(result.exit_code or 0))
        except Exception as e:
            return ProviderExecResult(output="", exit_code=1, error=str(e))

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
        sessions: list[SessionInfo] = []
        for sb in result.items:
            state = sb.state.value
            if state == "started":
                status = "running"
            elif state == "stopped":
                status = "paused"
            else:
                status = "unknown"
            sessions.append(SessionInfo(session_id=sb.id, provider=self.name, status=status))
        return sessions

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
