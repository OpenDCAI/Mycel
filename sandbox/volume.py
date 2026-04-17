"""SandboxVolume — provider-agnostic mount/sync engine.

"Mount" is abstract: make a manager-supplied source path visible inside the sandbox.
Docker uses bind mount, E2B uses tar sync, Daytona uses managed volume.
SandboxVolume smooths over these differences.

This is sandbox infrastructure. It doesn't know what's being mounted
(files, code, data) — that's decided by the application layer.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SandboxVolume:
    """Provider-agnostic volume engine.

    Created once per SandboxManager (per provider).
    Source paths are resolved by SandboxManager and passed to operations.
    """

    def __init__(self, provider, provider_capability):
        self.provider = provider
        self.capability = provider_capability
        from sandbox.sync.manager import SyncManager

        self._sync = SyncManager(provider_capability=provider_capability)

    def mount(self, thread_id: str, source_path: Path | None, target_path: str) -> None:
        """Make source_path visible at target_path inside sandbox.
        local: no-op. providers without mount support: no-op (sync handles it).
        docker/daytona with mount: bind mount.
        """
        if self.capability.runtime_kind == "local":
            return
        if source_path is None or not self.capability.mount.supports_mount:
            return
        from sandbox.config import MountSpec

        self.provider.set_thread_bind_mounts(
            thread_id,
            [MountSpec(source=str(source_path), target=target_path, read_only=False)],
        )

    def mount_managed_volume(self, thread_id: str, backend_ref: str, target_path: str) -> None:
        """Mount provider-managed persistent volume."""
        self.provider.set_managed_volume_mount(thread_id, backend_ref, target_path)

    def resolve_mount_path(self) -> str:
        """Container-side path where volumes are mounted."""
        return getattr(self.provider, "WORKSPACE_ROOT", "/workspace") + "/files"

    def sync_upload(self, thread_id: str, session_id: str, source_path: Path, remote_path: str, files: list[str] | None = None) -> None:
        """Sync files from local staging path to sandbox."""
        self._sync.upload(source_path, remote_path, session_id, self.provider, files=files, state_key=thread_id)

    def sync_download(self, thread_id: str, session_id: str, source_path: Path, remote_path: str) -> None:
        """Sync files from sandbox back to local staging path."""
        self._sync.download(source_path, remote_path, session_id, self.provider, state_key=thread_id)

    def clear_sync_state(self, thread_id: str) -> None:
        """Remove all sync tracking state for a thread."""
        self._sync.clear_state(thread_id)
