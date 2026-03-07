import pytest
from pathlib import Path
from sandbox.workspace_sync import WorkspaceSync
from sandbox.provider import ProviderCapability, MountCapability


def test_workspace_sync_initialization():
    """WorkspaceSync should initialize with provider and workspace path."""
    capability = ProviderCapability(
        can_pause=True,
        can_resume=True,
        can_destroy=True,
        mount=MountCapability(supports_mount=True)
    )

    sync = WorkspaceSync(
        provider_capability=capability,
        workspace_root=Path("/tmp/test-workspace")
    )

    assert sync.provider_capability == capability
    assert sync.workspace_root == Path("/tmp/test-workspace")


def test_get_thread_workspace_path():
    """Should resolve thread-specific workspace directory."""
    sync = WorkspaceSync(
        provider_capability=ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
        ),
        workspace_root=Path("/tmp/workspaces")
    )

    path = sync.get_thread_workspace_path("thread-123")
    assert path == Path("/tmp/workspaces/thread-123/files")
