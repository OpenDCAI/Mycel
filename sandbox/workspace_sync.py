"""Workspace synchronization across different sandbox providers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sandbox.provider import ProviderCapability, SandboxProvider


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

    def upload_workspace(self, thread_id: str, session_id: str, provider: SandboxProvider) -> None:
        """Upload workspace files to sandbox."""
        if not self.needs_upload_sync():
            return
        workspace = self.get_thread_workspace_path(thread_id)
        if not workspace.exists():
            return
        for file_path in workspace.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(workspace)
                remote_path = f"/workspace/files/{relative}"
                content = file_path.read_text()
                provider.write_file(session_id, remote_path, content)
