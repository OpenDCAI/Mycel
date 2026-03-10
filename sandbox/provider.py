"""Abstract sandbox provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from sandbox.runtime import PhysicalTerminalRuntime
    from sandbox.lease import SandboxLease
    from sandbox.terminal import AbstractTerminal

RESOURCE_CAPABILITY_KEYS = (
    "filesystem",
    "terminal",
    "metrics",
    "screenshot",
    "web",
    "process",
    "hooks",
    "snapshot",
)


def normalize_resource_capabilities(raw: Mapping[str, object]) -> dict[str, bool]:
    missing = [key for key in RESOURCE_CAPABILITY_KEYS if key not in raw]
    extras = [key for key in raw if key not in RESOURCE_CAPABILITY_KEYS]
    if missing or extras:
        raise RuntimeError(f"Invalid resource capabilities; missing={missing}, extras={extras}")
    # @@@capability-shape-contract - monitor/UI rely on fixed capability keys for stable rendering.
    return {key: bool(raw[key]) for key in RESOURCE_CAPABILITY_KEYS}


def build_resource_capabilities(
    *,
    filesystem: bool,
    terminal: bool,
    metrics: bool,
    screenshot: bool,
    web: bool,
    process: bool,
    hooks: bool,
    snapshot: bool,
) -> dict[str, bool]:
    return normalize_resource_capabilities(
        {
            "filesystem": filesystem,
            "terminal": terminal,
            "metrics": metrics,
            "screenshot": screenshot,
            "web": web,
            "process": process,
            "hooks": hooks,
            "snapshot": snapshot,
        }
    )


@dataclass(frozen=True)
class MountCapability:
    """Mount behavior capability shared across providers."""

    supports_mount: bool = False
    supports_copy: bool = False
    supports_read_only: bool = False
    mode_handlers: dict[str, bool] = field(default_factory=dict)
    supports_workplace: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "supports_mount": self.supports_mount,
            "supports_copy": self.supports_copy,
            "supports_read_only": self.supports_read_only,
            "mode_handlers": dict(self.mode_handlers or {}),
            "supports_workplace": self.supports_workplace,
        }


@dataclass(frozen=True)
class ProviderCapability:
    """Declared lifecycle capability of a provider implementation."""

    can_pause: bool
    can_resume: bool
    can_destroy: bool
    supports_webhook: bool = False
    supports_status_probe: bool = True
    eager_instance_binding: bool = False
    inspect_visible: bool = True
    runtime_kind: str = "remote"
    resource_capabilities: dict[str, bool] = field(default_factory=dict)
    mount: MountCapability = field(default_factory=MountCapability)

    def declared_resource_capabilities(self) -> dict[str, bool]:
        return normalize_resource_capabilities(self.resource_capabilities)


@dataclass
class SessionInfo:
    session_id: str
    provider: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderExecResult:
    output: str
    exit_code: int = 0
    error: str | None = None


@dataclass
class Metrics:
    cpu_percent: float | None = None
    memory_used_mb: float | None = None
    memory_total_mb: float | None = None
    disk_used_gb: float | None = None
    disk_total_gb: float | None = None
    network_rx_kbps: float | None = None
    network_tx_kbps: float | None = None


class SandboxProvider(ABC):
    """Abstract interface for sandbox providers."""

    name: str  # Provider identifier: 'agentbay', 'e2b', 'docker', 'local'
    WORKSPACE_ROOT: str = "/workspace"  # Override in subclasses with non-standard workspace paths

    @abstractmethod
    def get_capability(self) -> ProviderCapability:
        """Return lifecycle capability contract for this provider."""
        pass

    @abstractmethod
    def create_session(self, context_id: str | None = None, thread_id: str | None = None) -> SessionInfo:
        pass

    @abstractmethod
    def destroy_session(self, session_id: str, sync: bool = True) -> bool:
        pass

    @abstractmethod
    def pause_session(self, session_id: str) -> bool:
        pass

    @abstractmethod
    def resume_session(self, session_id: str) -> bool:
        pass

    @abstractmethod
    def get_session_status(self, session_id: str) -> str:
        pass

    @abstractmethod
    def execute(
        self,
        session_id: str,
        command: str,
        timeout_ms: int = 30000,
        cwd: str | None = None,
    ) -> ProviderExecResult:
        pass

    @abstractmethod
    def read_file(self, session_id: str, path: str) -> str:
        pass

    @abstractmethod
    def write_file(self, session_id: str, path: str, content: str) -> str:
        pass

    @abstractmethod
    def list_dir(self, session_id: str, path: str) -> list[dict]:
        pass

    @abstractmethod
    def get_metrics(self, session_id: str) -> Metrics | None:
        pass

    @abstractmethod
    def create_runtime(self, terminal: AbstractTerminal, lease: SandboxLease) -> PhysicalTerminalRuntime:
        """Create the appropriate PhysicalTerminalRuntime for this provider."""
        pass

    def get_metrics_via_commands(self, session_id: str) -> Metrics | None:
        """Get metrics by running Linux shell commands inside the sandbox."""
        try:
            cpu_result = self.execute(
                session_id,
                "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'",
                timeout_ms=5000,
            )
            cpu_percent = float(cpu_result.output.strip()) if cpu_result.exit_code == 0 and cpu_result.output.strip() else None

            mem_result = self.execute(session_id, "free -m | awk 'NR==2{print $3,$2}'", timeout_ms=5000)
            memory_used_mb, memory_total_mb = None, None
            if mem_result.exit_code == 0 and mem_result.output.strip():
                parts = mem_result.output.strip().split()
                memory_used_mb = float(parts[0]) if len(parts) > 0 else None
                memory_total_mb = float(parts[1]) if len(parts) > 1 else None

            disk_result = self.execute(session_id, "df -BG / | awk 'NR==2{gsub(/G/,\"\"); print $3,$2}'", timeout_ms=5000)
            disk_used_gb, disk_total_gb = None, None
            if disk_result.exit_code == 0 and disk_result.output.strip():
                parts = disk_result.output.strip().split()
                disk_used_gb = float(parts[0]) if len(parts) > 0 else None
                disk_total_gb = float(parts[1]) if len(parts) > 1 else None

            if any(v is not None for v in [cpu_percent, memory_used_mb, disk_used_gb]):
                return Metrics(
                    cpu_percent=cpu_percent,
                    memory_used_mb=memory_used_mb,
                    memory_total_mb=memory_total_mb,
                    disk_used_gb=disk_used_gb,
                    disk_total_gb=disk_total_gb,
                )
            return None
        except Exception:
            return None

    def screenshot(self, session_id: str) -> bytes | None:
        return None

    def list_processes(self, session_id: str) -> list[dict]:
        return []

    def get_web_url(self, session_id: str) -> str | None:
        return None

    def create_workplace(self, member_name: str, mount_path: str) -> str:
        """Create persistent storage for an agent. Returns backend_ref.
        Override in providers where supports_workplace=True.
        """
        raise NotImplementedError(f"{self.name} does not support Workplaces")

    def set_workplace_mount(self, thread_id: str, backend_ref: str, mount_path: str) -> None:
        """Configure workplace mount for next create_session().
        Called before create_session(). Provider stores this internally.
        """
        raise NotImplementedError(f"{self.name} does not support Workplaces")

    def delete_workplace(self, backend_ref: str) -> None:
        """Delete persistent storage. Called on agent deletion."""
        raise NotImplementedError(f"{self.name} does not support Workplaces")
