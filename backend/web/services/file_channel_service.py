"""File channel service — per-lease file storage and sync orchestration.

Each sandbox lease owns a file channel (stored in the file_channels table).
User uploads → VolumeSource (host disk) → sync/mount into sandbox → agent reads.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from backend.web.utils.helpers import _get_container


# ---------------------------------------------------------------------------
# Lease-based file channel lookup
# ---------------------------------------------------------------------------


def _get_file_channel(thread_id: str) -> tuple["VolumeSource", str]:
    """Get (VolumeSource, channel_id) for a thread via lease chain.

    Chain: thread → active terminal → lease → file_channel_id → file_channels.source → deserialize.
    """
    import json
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

    channel_id = lease.file_channel_id
    if not channel_id:
        raise ValueError(f"Lease {terminal.lease_id} has no file_channel_id")

    repo = _get_container().file_channel_repo()
    try:
        entry = repo.get(channel_id)
    finally:
        repo.close()

    if not entry:
        raise ValueError(f"File channel not found: {channel_id}")

    return deserialize_volume_source(json.loads(entry["source"])), channel_id


def get_file_channel_source(thread_id: str) -> "VolumeSource":
    """Get VolumeSource for a thread via lease chain.

    This is the primary way all code paths (upload, sync, pause, resume) get the VolumeSource.
    """
    source, _ = _get_file_channel(thread_id)
    return source


# ---------------------------------------------------------------------------
# Sandbox mount orchestration
# ---------------------------------------------------------------------------


def setup_sandbox_mounts(
    thread_id: str,
    engine: "FileChannelEngine",
) -> dict:
    """Called at sandbox startup. Mount the lease's file channel into the sandbox.

    For Daytona: first startup upgrades HostVolume → DaytonaVolume.
    For Docker/others with bind mount: bind-mounts the volume dir.
    For E2B/AgentBay (no mount support): no-op here, sync handles it.
    """
    from sandbox.volume_source import DaytonaVolume

    source, channel_id = _get_file_channel(thread_id)
    remote_path = engine.resolve_channel_path()

    # Daytona upgrade: first startup creates managed volume
    if (engine.capability.runtime_kind == "daytona_pty"
            and not isinstance(source, DaytonaVolume)):
        source = _upgrade_to_daytona_volume(
            thread_id, current_source=source, provider=engine.provider,
            channel_id=channel_id, remote_path=remote_path,
        )

    # Mount
    if isinstance(source, DaytonaVolume):
        engine.mount_managed_volume(thread_id, source.volume_name, remote_path)
    else:
        engine.mount(thread_id, source, remote_path)

    return {"source": source, "remote_path": remote_path}


def _upgrade_to_daytona_volume(thread_id, current_source, provider, channel_id: str, remote_path: str):
    """First Daytona sandbox start: create managed volume, upgrade VolumeSource in DB."""
    import json
    from sandbox.volume_source import DaytonaVolume

    from backend.web.utils.helpers import load_thread_config
    tc = load_thread_config(thread_id)
    member_id = tc.get("member_id", "unknown") if tc else "unknown"

    try:
        volume_name = provider.create_managed_volume(member_id, remote_path)
    except Exception as e:
        if "already exists" in str(e):
            volume_name = f"leon-volume-{member_id}"
            logger.info("Daytona volume already exists: %s, reusing", volume_name)
        else:
            raise

    new_source = DaytonaVolume(
        staging_path=current_source.host_path,
        volume_name=volume_name,
    )

    repo = _get_container().file_channel_repo()
    try:
        repo.update_source(channel_id, json.dumps(new_source.serialize()))
    finally:
        repo.close()

    return new_source


# ---------------------------------------------------------------------------
# File CRUD — delegates to VolumeSource via lease lookup
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
