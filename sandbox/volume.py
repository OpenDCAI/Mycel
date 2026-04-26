from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SandboxVolume:
    def __init__(self, provider, provider_capability):
        self.provider = provider
        self.capability = provider_capability
        from sandbox.sync.manager import SyncManager

        self._sync = SyncManager(provider_capability=provider_capability)

    def mount(self, thread_id: str, source_path: Path | None, target_path: str) -> None:
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
        self.provider.set_managed_volume_mount(thread_id, backend_ref, target_path)

    def resolve_mount_path(self) -> str:
        return getattr(self.provider, "WORKSPACE_ROOT", "/workspace") + "/files"

    def sync_upload(self, thread_id: str, session_id: str, source_path: Path, remote_path: str, files: list[str] | None = None) -> None:
        self._sync.upload(source_path, remote_path, session_id, self.provider, files=files, state_key=thread_id)

    def sync_download(self, thread_id: str, session_id: str, source_path: Path, remote_path: str) -> None:
        self._sync.download(source_path, remote_path, session_id, self.provider, state_key=thread_id)

    def clear_sync_state(self, thread_id: str) -> None:
        self._sync.clear_state(thread_id)
