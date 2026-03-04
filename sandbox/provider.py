"""Abstract sandbox provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping

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
    cpu_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_used_gb: float
    disk_total_gb: float
    network_rx_kbps: float
    network_tx_kbps: float


class SandboxProvider(ABC):
    """Abstract interface for sandbox providers."""

    name: str  # Provider identifier: 'agentbay', 'e2b', 'docker', 'local'

    @abstractmethod
    def get_capability(self) -> ProviderCapability:
        """Return lifecycle capability contract for this provider."""
        pass

    @abstractmethod
    def create_session(self, context_id: str | None = None) -> SessionInfo:
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

    def screenshot(self, session_id: str) -> bytes | str | None:
        return None

    def list_processes(self, session_id: str) -> list[dict]:
        return []

    def get_web_url(self, session_id: str) -> str | None:
        return None
