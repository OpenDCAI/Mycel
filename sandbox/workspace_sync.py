"""Workspace synchronization across different sandbox providers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sandbox.provider import ProviderCapability, SandboxProvider

logger = logging.getLogger(__name__)


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
        # Only Docker uses host bind mounts; remote providers need SDK upload
        return self.provider_capability.runtime_kind not in ("local", "docker")

    def upload_workspace(self, thread_id: str, session_id: str, provider: SandboxProvider) -> None:
        """Upload workspace files to sandbox."""
        try:
            if not self.needs_upload_sync():
                return
            workspace = self.get_thread_workspace_path(thread_id)
            if not workspace.exists():
                logger.debug(f"No workspace to upload for thread {thread_id}")
                return

            # @@@workspace-root - E2B uses /home/user/workspace, others use /workspace
            workspace_root = getattr(provider, 'WORKSPACE_ROOT', '/workspace') + '/files'
            # Ensure remote directory exists (some providers don't auto-create parents)
            if hasattr(provider, 'execute'):
                provider.execute(session_id, f"mkdir -p {workspace_root}")

            file_count = 0
            for file_path in workspace.rglob("*"):
                if file_path.is_file():
                    relative = file_path.relative_to(workspace)
                    remote_path = f"{workspace_root}/{relative}"
                    content = file_path.read_text()
                    provider.write_file(session_id, remote_path, content)
                    file_count += 1

            logger.info(f"Uploaded {file_count} files to sandbox {session_id}")
        except Exception as e:
            logger.error(f"Failed to upload workspace for thread {thread_id}: {e}")
            raise

    def download_workspace(self, thread_id: str, session_id: str, provider: SandboxProvider) -> None:
        """Download workspace files from sandbox."""
        try:
            if not self.needs_upload_sync():
                return
            workspace = self.get_thread_workspace_path(thread_id)
            workspace.mkdir(parents=True, exist_ok=True)

            file_count = 0

            def download_recursive(remote_path: str, local_path: Path) -> None:
                nonlocal file_count
                items = provider.list_dir(session_id, remote_path)
                for item in items:
                    remote_item = f"{remote_path}/{item['name']}".replace("//", "/")
                    local_item = local_path / item["name"]
                    if item["type"] == "directory":
                        local_item.mkdir(parents=True, exist_ok=True)
                        download_recursive(remote_item, local_item)
                    else:
                        content = provider.read_file(session_id, remote_item)
                        local_item.write_text(content)
                        file_count += 1

            # @@@workspace-root - E2B uses /home/user/workspace, others use /workspace
            workspace_root = getattr(provider, 'WORKSPACE_ROOT', '/workspace') + '/files'
            download_recursive(workspace_root, workspace)
            logger.info(f"Downloaded {file_count} files from sandbox {session_id}")
        except Exception as e:
            logger.error(f"Failed to download workspace for thread {thread_id}: {e}")
            raise
