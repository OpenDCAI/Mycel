"""
Docker sandbox provider.

Implements SandboxProvider using local Docker containers.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import uuid

from sandbox.provider import (
    Metrics,
    ProviderCapability,
    ProviderExecResult,
    SandboxProvider,
    SessionInfo,
    build_resource_capabilities,
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
            snapshot=False,
        ),
    )

    def get_capability(self) -> ProviderCapability:
        return self.CAPABILITY

    def __init__(
        self,
        image: str,
        mount_path: str = "/workspace",
        command_timeout_sec: float = 20.0,
        provider_name: str | None = None,
        docker_host: str | None = None,
    ):
        if provider_name:
            self.name = provider_name
        self.image = image
        self.mount_path = mount_path
        self.command_timeout_sec = command_timeout_sec
        self._docker_host = docker_host
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
            # @@@context-label - also label with context_id so probe can find container via lease_id
            cmd.extend(["--label", f"leon.context_id={context_id}"])
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
        # @@@docker-host - pass DOCKER_HOST when configured to bypass stuck Docker Desktop context
        env = None
        if self._docker_host:
            env = os.environ.copy()
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
