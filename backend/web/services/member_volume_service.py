"""Member volume service — persistent storage for agent members."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

from backend.web.utils.helpers import _get_container
from storage.contracts import MemberVolumeRepo


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _member_volume_repo() -> MemberVolumeRepo:
    return _get_container().member_volume_repo()


def get_member_volume(member_id: str, provider_type: str) -> dict[str, Any] | None:
    repo = _member_volume_repo()
    try:
        return repo.get(member_id, provider_type)
    finally:
        repo.close()


def create_member_volume(
    member_id: str, provider_type: str, backend_ref: str, mount_path: str,
) -> dict[str, Any]:
    now = _now_utc()
    repo = _member_volume_repo()
    try:
        repo.upsert(member_id, provider_type, backend_ref, mount_path, now)
    finally:
        repo.close()
    logger.info("Created member volume: member_id=%s provider=%s ref=%s", member_id, provider_type, backend_ref)
    return {
        "member_id": member_id, "provider_type": provider_type,
        "backend_ref": backend_ref, "mount_path": mount_path, "created_at": now,
    }


def list_member_volumes(member_id: str) -> list[dict[str, Any]]:
    repo = _member_volume_repo()
    try:
        return repo.list_by_member(member_id)
    finally:
        repo.close()


def delete_member_volume(member_id: str, provider_type: str) -> bool:
    repo = _member_volume_repo()
    try:
        deleted = repo.delete(member_id, provider_type)
    finally:
        repo.close()
    if deleted:
        logger.info("Deleted member volume: member_id=%s provider=%s", member_id, provider_type)
    return deleted


def delete_all_member_volumes(member_id: str) -> int:
    repo = _member_volume_repo()
    try:
        count = repo.delete_all_for_member(member_id)
    finally:
        repo.close()
    if count:
        logger.info("Deleted %d member volume(s) for member_id=%s", count, member_id)
    return count


# ---------------------------------------------------------------------------
# Orchestration — lease-based volume lookup + sandbox mount setup
# ---------------------------------------------------------------------------


def _get_lease_volume(thread_id: str) -> tuple["VolumeSource", str]:
    """Internal: get (VolumeSource, volume_id) for a thread via lease chain.

    Chain: thread → active terminal → lease → volume_id → sandbox_volumes.source → deserialize.
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

    return deserialize_volume_source(json.loads(entry["source"])), volume_id


def get_lease_volume_source(thread_id: str) -> "VolumeSource":
    """Get VolumeSource for a thread via lease chain.

    This is the primary way all code paths (upload, sync, pause, resume) get the VolumeSource.
    """
    source, _ = _get_lease_volume(thread_id)
    return source


def setup_sandbox_mounts(
    thread_id: str,
    sandbox_vol: "SandboxVolume",
) -> dict:
    """Called at sandbox startup. Mount the lease's volume into the sandbox.

    For Daytona: first startup upgrades HostVolume → DaytonaVolume.
    For Docker/others with bind mount: bind-mounts the volume dir.
    For E2B/AgentBay (no mount support): no-op here, sync handles it.
    """
    from sandbox.volume_source import DaytonaVolume

    source, volume_id = _get_lease_volume(thread_id)
    remote_path = sandbox_vol.resolve_remote_path()

    # Daytona upgrade: first startup creates managed volume
    if (sandbox_vol.capability.runtime_kind == "daytona_pty"
            and not isinstance(source, DaytonaVolume)):
        source = _upgrade_to_daytona_volume(
            thread_id, current_source=source, provider=sandbox_vol.provider,
            volume_id=volume_id, remote_path=remote_path,
        )

    # Mount
    if isinstance(source, DaytonaVolume):
        sandbox_vol.mount_volume(thread_id, source.volume_name, remote_path)
    else:
        sandbox_vol.mount(thread_id, source, remote_path)

    return {"source": source, "remote_path": remote_path}


def _upgrade_to_daytona_volume(thread_id, current_source, provider, volume_id: str, remote_path: str):
    """First Daytona sandbox start: create managed volume, upgrade VolumeSource in DB."""
    import json
    from sandbox.volume_source import DaytonaVolume

    # Get member_id from thread config for volume naming
    from backend.web.utils.helpers import load_thread_config
    tc = load_thread_config(thread_id)
    member_id = tc.get("member_id", "unknown") if tc else "unknown"

    try:
        volume_name = provider.create_member_volume(member_id, remote_path)
    except Exception as e:
        if "already exists" in str(e):
            # Reuse existing volume — name follows provider convention
            volume_name = f"leon-volume-{member_id}"
            logger.info("Daytona volume already exists: %s, reusing", volume_name)
        else:
            raise

    new_source = DaytonaVolume(
        staging_path=current_source.host_path,
        volume_name=volume_name,
    )

    # Update DB
    repo = _get_container().sandbox_volume_repo()
    try:
        repo.update_source(volume_id, json.dumps(new_source.serialize()))
    finally:
        repo.close()

    return new_source


# ---------------------------------------------------------------------------
# File CRUD — delegates to VolumeSource via lease lookup
# ---------------------------------------------------------------------------


def save_file(*, thread_id: str, relative_path: str, content: bytes) -> dict:
    """Save file to the thread's volume (via lease chain)."""
    source = get_lease_volume_source(thread_id)
    result = source.save_file(relative_path, content)
    result["thread_id"] = thread_id
    from backend.web.services.activity_tracker import track_thread_activity
    track_thread_activity(thread_id, "file_upload")
    return result


def list_volume_files(*, thread_id: str) -> list[dict]:
    """List files in the thread's volume."""
    return get_lease_volume_source(thread_id).list_files()


def resolve_volume_file(*, thread_id: str, relative_path: str):
    """Resolve file path in the thread's volume."""
    return get_lease_volume_source(thread_id).resolve_file(relative_path)


def delete_volume_file(*, thread_id: str, relative_path: str) -> None:
    """Delete file from the thread's volume."""
    get_lease_volume_source(thread_id).delete_file(relative_path)
