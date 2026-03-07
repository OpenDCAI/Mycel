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


def test_needs_upload_sync_for_bind_mount():
    """Bind mount providers don't need upload sync."""
    sync = WorkspaceSync(
        provider_capability=ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
            mount=MountCapability(supports_mount=True)
        ),
        workspace_root=Path("/tmp/workspaces")
    )

    assert sync.needs_upload_sync() is False


def test_needs_upload_sync_for_remote():
    """Remote providers need upload sync."""
    sync = WorkspaceSync(
        provider_capability=ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
            mount=MountCapability(supports_mount=False, supports_copy=True)
        ),
        workspace_root=Path("/tmp/workspaces")
    )

    assert sync.needs_upload_sync() is True
