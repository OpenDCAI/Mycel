from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from config.user_paths import user_home_path
from storage.container_cache import get_storage_container as _get_container

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileChannelBinding:
    thread_id: str
    workspace_id: str
    workspace_path: str
    local_staging_root: Path | None
    remote_files_dir: str


def get_file_channel_source(thread_id: str):
    from sandbox.volume_source import HostVolume

    binding = get_file_channel_binding(thread_id)
    if binding.local_staging_root is None:
        raise ValueError("file_channel.local_staging_root is required")
    return HostVolume(binding.local_staging_root)


def get_file_channel_binding(thread_id: str) -> FileChannelBinding:
    container = _get_container()
    thread_repo = container.thread_repo()
    try:
        thread_row = thread_repo.get_by_id(thread_id)
    finally:
        close = getattr(thread_repo, "close", None)
        if callable(close):
            close()
    if thread_row is None:
        raise ValueError(f"Thread not found: {thread_id}")

    workspace_id = _required_text(thread_row, "current_workspace_id", "thread")

    workspace_repo = container.workspace_repo()
    try:
        workspace_row = workspace_repo.get_by_id(workspace_id)
    finally:
        close = getattr(workspace_repo, "close", None)
        if callable(close):
            close()
    if workspace_row is None:
        raise ValueError(f"Workspace not found: {workspace_id}")

    return FileChannelBinding(
        thread_id=thread_id,
        workspace_id=workspace_id,
        workspace_path=_required_text(workspace_row, "workspace_path", "workspace"),
        local_staging_root=user_home_path("file_channels", workspace_id).expanduser().resolve(),
        remote_files_dir="/workspace/files",
    )


def save_file(*, thread_id: str, relative_path: str, content: bytes) -> dict:
    source = get_file_channel_source(thread_id)
    result = source.save_file(relative_path, content)
    result["thread_id"] = thread_id
    return result


def _required_text(row, key: str, label: str) -> str:
    value = row.get(key) if isinstance(row, dict) else getattr(row, key, None)
    if isinstance(value, str):
        value = value.strip()
    if value in (None, ""):
        raise ValueError(f"{label}.{key} is required")
    return str(value)
