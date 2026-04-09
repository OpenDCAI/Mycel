"""File channel service — per-lease file storage for user↔agent file transfer.

File channel is an application-layer concept. Under the hood it uses
sandbox volumes (VolumeSource + SandboxVolume mount/sync engine).
This service provides the app-layer API for file CRUD on a thread's channel.
"""

from __future__ import annotations

import json
import logging

from backend.web.utils.helpers import _get_container
from storage.runtime import build_lease_repo as make_lease_repo
from storage.runtime import build_terminal_repo as make_terminal_repo

logger = logging.getLogger(__name__)


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
    return _resolve_volume_source(thread_id)


# ---------------------------------------------------------------------------
# File CRUD — delegates to VolumeSource
# ---------------------------------------------------------------------------


def save_file(*, thread_id: str, relative_path: str, content: bytes) -> dict:
    """Save file to the thread's file channel."""
    source = get_file_channel_source(thread_id)
    result = source.save_file(relative_path, content)
    result["thread_id"] = thread_id
    from backend.web.services.activity_tracker import track_thread_activity

    track_thread_activity(thread_id, "file_upload")
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
