"""File channel service for workspace-owned user↔agent file transfer."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from backend.web.utils.helpers import _get_container
from config.user_paths import user_home_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileChannelBinding:
    thread_id: str
    workspace_id: str
    workspace_path: str
    local_staging_root: Path | None
    remote_files_dir: str


def get_file_channel_source(thread_id: str):
    """Get the local file-channel source for a thread."""
    from sandbox.volume_source import HostVolume

    binding = get_file_channel_binding(thread_id)
    return HostVolume(_required_path(binding.local_staging_root, "file_channel.local_staging_root"))


def get_file_channel_binding(thread_id: str) -> FileChannelBinding:
    """Resolve split file-channel truth for a thread.

    Ownership/binding lives on the thread -> workspace edge.
    Host staging remains whatever local file root the current runtime uses.
    """
    container = _get_container()
    thread_repo = container.thread_repo()
    try:
        thread_row = thread_repo.get_by_id(thread_id)
    finally:
        _close_repo(thread_repo)
    if thread_row is None:
        raise ValueError(f"Thread not found: {thread_id}")

    workspace_id = _required_text(thread_row, "current_workspace_id", "thread")

    workspace_repo = container.workspace_repo()
    try:
        workspace_row = workspace_repo.get_by_id(workspace_id)
    finally:
        _close_repo(workspace_repo)
    if workspace_row is None:
        raise ValueError(f"Workspace not found: {workspace_id}")

    return FileChannelBinding(
        thread_id=thread_id,
        workspace_id=workspace_id,
        workspace_path=_required_text(workspace_row, "workspace_path", "workspace"),
        local_staging_root=_workspace_file_channel_root(workspace_id),
        remote_files_dir="/workspace/files",
    )


# ---------------------------------------------------------------------------
# File CRUD — delegates to VolumeSource
# ---------------------------------------------------------------------------


def save_file(*, thread_id: str, relative_path: str, content: bytes) -> dict:
    """Save file to the thread's file channel."""
    source = get_file_channel_source(thread_id)
    result = source.save_file(relative_path, content)
    result["thread_id"] = thread_id
    return result


def list_channel_files(*, thread_id: str) -> list[dict]:
    """List files in the thread's file channel."""
    return get_file_channel_source(thread_id).list_files()


def resolve_channel_file(*, thread_id: str, relative_path: str):
    """Resolve file path in the thread's file channel."""
    return get_file_channel_source(thread_id).resolve_file(relative_path)


def delete_channel_file(*, thread_id: str, relative_path: str) -> None:
    """Delete file from the thread's file channel."""
    get_file_channel_source(thread_id).delete_file(relative_path)


def _row_value(row, key: str):
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _required_text(row, key: str, label: str) -> str:
    value = _row_value(row, key)
    if isinstance(value, str):
        value = value.strip()
    if value in (None, ""):
        raise ValueError(f"{label}.{key} is required")
    return str(value)


def _required_path(value: Path | None, label: str) -> Path:
    if value is None:
        raise ValueError(f"{label} is required")
    return value


def _workspace_file_channel_root(workspace_id: str) -> Path:
    return user_home_path("file_channels", workspace_id).expanduser().resolve()


def _close_repo(repo) -> None:
    close = getattr(repo, "close", None)
    if callable(close):
        close()
