"""Workspace synchronization across different sandbox providers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sandbox.provider import ProviderCapability


class WorkspaceSync:
    """Handles workspace file synchronization between backend and sandbox."""

    def __init__(
        self,
        provider_capability: ProviderCapability,
        workspace_root: Path,
    ):
        self.provider_capability = provider_capability
        self.workspace_root = workspace_root

    def get_thread_workspace_path(self, thread_id: str) -> Path:
        """Get the local workspace directory for a thread."""
        return self.workspace_root / thread_id / "files"

    def needs_upload_sync(self) -> bool:
        """Check if provider needs explicit upload sync (vs bind mount)."""
        return not self.provider_capability.mount.supports_mount
