"""File channel service — per-lease file storage for user↔agent file transfer.

File channel is an application-layer concept. Under the hood it uses
sandbox volumes (VolumeSource + SandboxVolume mount/sync engine).
This service provides the app-layer API for file CRUD on a thread's channel.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from backend.web.utils.helpers import _get_container
from config.user_paths import user_home_path
from sandbox.clock import utc_now_iso
from sandbox.control_plane_repos import make_lease_repo, make_terminal_repo
from storage.runtime import build_chat_session_repo as make_chat_session_repo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileChannelBinding:
    thread_id: str
    workspace_id: str
    workspace_path: str
    local_staging_root: Path | None
    remote_files_dir: str


def _resolve_volume_source(thread_id: str):
    """Resolve VolumeSource for a thread via lease chain.

    This is the application-layer entry point. Uses sandbox-layer stores
    to walk: thread → terminal → lease → volume_id → sandbox_volumes.
    """
    from sandbox.volume_source import deserialize_volume_source

    terminal_repo = make_terminal_repo()
    try:
        terminal_row = terminal_repo.get_active(thread_id)
    finally:
        terminal_repo.close()
    if not terminal_row:
        raise ValueError(f"No active terminal for thread {thread_id}")

    lease_repo = make_lease_repo()
    try:
        lease_row = lease_repo.get(terminal_row["lease_id"])
    finally:
        lease_repo.close()
    if not lease_row:
        raise ValueError(f"Lease not found: {terminal_row['lease_id']}")
    volume_id = lease_row.get("volume_id")
    if not volume_id:
        raise ValueError(f"Lease {terminal_row['lease_id']} has no volume_id")

    repo = _get_container().sandbox_volume_repo()
    try:
        entry = repo.get(volume_id)
    finally:
        repo.close()

    if not entry:
        raise ValueError(f"Volume not found: {volume_id}")

    return deserialize_volume_source(json.loads(entry["source"]))


def get_file_channel_source(thread_id: str):
    """Get VolumeSource for a thread's file channel.

    Primary entry point for all app-layer code paths (upload, list, download, delete).
    """
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

    repo = make_chat_session_repo()
    try:
        repo.touch_thread_activity(thread_id, utc_now_iso())
    finally:
        repo.close()
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
