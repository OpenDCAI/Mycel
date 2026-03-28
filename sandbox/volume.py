"""SandboxVolume — provider-agnostic mount/sync engine.

"Mount" is abstract: establish persistent storage for the sandbox.
Docker uses bind mount, E2B uses tar sync, Daytona uses managed volume.
SandboxVolume smooths over these differences.

File CRUD delegated to VolumeSource (HostVolume, DaytonaVolume, etc.).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sandbox.volume_source import VolumeSource

logger = logging.getLogger(__name__)


class SandboxVolume:
    """Provider-agnostic volume engine.

    Created once per SandboxManager (per provider).
    VolumeSource is per-thread, passed to operations or resolved from DB.
    """

    def __init__(self, provider, provider_capability):
        self.provider = provider
        self.capability = provider_capability
        from sandbox.sync.manager import SyncManager
        self.sync = SyncManager(provider_capability=provider_capability)

    def mount(self, thread_id: str, source: VolumeSource, target_path: str) -> None:
        """Make source visible at target_path inside sandbox.
        local: no-op. providers without mount support: no-op (sync handles it).
        docker/daytona with mount: bind mount.
        """
        if self.capability.runtime_kind == "local":
            return
        host = source.host_path
        if not host or not self.capability.mount.supports_mount:
            return
        from sandbox.config import MountSpec
        self.provider.set_thread_bind_mounts(thread_id, [
            MountSpec(source=str(host), target=target_path, read_only=False)
        ])

    def mount_volume(self, thread_id: str, backend_ref: str, target_path: str) -> None:
        """Mount provider-managed persistent volume."""
        self.provider.set_volume_mount(thread_id, backend_ref, target_path)

    def resolve_remote_path(self) -> str:
        """Container-side path where files appear."""
        return getattr(self.provider, "WORKSPACE_ROOT", "/workspace") + "/files"

    def sync_upload(self, thread_id: str, session_id: str,
                    source: VolumeSource, remote_path: str,
                    files: list[str] | None = None) -> None:
        """Sync files from VolumeSource to sandbox."""
        host = source.host_path
        if not host:
            return
        self.sync.upload(host, remote_path, session_id, self.provider,
                         files=files, state_key=thread_id)

    def sync_download(self, thread_id: str, session_id: str,
                      source: VolumeSource, remote_path: str) -> None:
        """Sync files from sandbox back to VolumeSource."""
        host = source.host_path
        if not host:
            return
        self.sync.download(host, remote_path, session_id, self.provider,
                           state_key=thread_id)

    def clear_sync_state(self, thread_id: str) -> None:
        """Remove all sync tracking state for a thread."""
        self.sync.clear_state(thread_id)
