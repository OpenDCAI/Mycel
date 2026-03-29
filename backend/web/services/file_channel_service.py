"""File channel service — per-lease file storage for user↔agent file transfer.

File channel is an application-layer concept. Under the hood it uses
sandbox volumes (VolumeSource + SandboxVolume mount/sync engine).
This service provides the app-layer API for file CRUD on a thread's channel.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

from backend.web.utils.helpers import _get_container


def _resolve_volume_source(thread_id: str):
    """Resolve VolumeSource for a thread via lease chain.

    This is the application-layer entry point. Uses sandbox-layer stores
    to walk: thread → terminal → lease → volume_id → sandbox_volumes.
    """
    from sandbox.terminal import TerminalStore
    from sandbox.lease import LeaseStore
    from sandbox.config import DEFAULT_DB_PATH
    from sandbox.volume_source import deserialize_volume_source

    terminal_store = TerminalStore(db_path=DEFAULT_DB_PATH)
    terminal = terminal_store.get_active(thread_id)
    if not terminal:
        raise ValueError(f"No active terminal for thread {thread_id}")

    lease_store = LeaseStore(db_path=DEFAULT_DB_PATH)
    lease = lease_store.get(terminal.lease_id)
    if not lease:
        raise ValueError(f"Lease not found: {terminal.lease_id}")

    volume_id = lease.volume_id
    if not volume_id:
        raise ValueError(f"Lease {terminal.lease_id} has no volume_id")

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
