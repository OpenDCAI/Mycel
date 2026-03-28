"""Sandbox files service — thread-scoped file storage.

A sandbox_files entry is a named directory on the host machine that can be shared
across multiple threads. Each thread can have at most one sandbox_files_id; multiple
threads can reference the same entry.

Files path is derived, not cached in DB:
  - thread has sandbox_files_id → entry.host_path
  - otherwise → SANDBOX_FILES_ROOT / thread_id / files
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from backend.web.core.config import SANDBOX_VOLUME_ROOT as SANDBOX_FILES_ROOT
from backend.web.utils.helpers import _get_container
from storage.contracts import SandboxVolumeRepo as SandboxFilesRepo


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _sandbox_files_repo() -> SandboxFilesRepo:
    return _get_container().sandbox_files_repo()


# ---------------------------------------------------------------------------
# Sandbox Files CRUD
# ---------------------------------------------------------------------------


def _create_sandbox_files_entry(host_path: str, name: str | None = None) -> dict[str, Any]:
    """Internal: Create sandbox files entity. Used by thread operations only."""
    host = Path(host_path).expanduser().resolve()
    if not host.exists():
        raise ValueError(f"Sandbox files host_path does not exist: {host}")
    sandbox_files_id = str(uuid.uuid4())
    now = _now_utc()
    repo = _sandbox_files_repo()
    try:
        repo.create(sandbox_files_id, str(host), name, now)
    finally:
        repo.close()
    return {"sandbox_files_id": sandbox_files_id, "host_path": str(host), "name": name, "created_at": now}


def _get_sandbox_files_entry(sandbox_files_id: str) -> dict[str, Any] | None:
    """Internal: Lookup sandbox files entity."""
    repo = _sandbox_files_repo()
    try:
        return repo.get(sandbox_files_id)
    finally:
        repo.close()


def _list_sandbox_files_entries() -> list[dict[str, Any]]:
    """Internal: List all sandbox files entities."""
    repo = _sandbox_files_repo()
    try:
        return repo.list_all()
    finally:
        repo.close()


def _delete_sandbox_files_entry(sandbox_files_id: str) -> bool:
    """Internal: Delete sandbox files entity (does not remove host directory)."""
    repo = _sandbox_files_repo()
    try:
        return repo.delete(sandbox_files_id)
    finally:
        repo.close()


def create_sandbox_files(thread_id: str) -> str:
    """Create sandbox files for thread. Returns sandbox_files_id."""
    host_path = SANDBOX_FILES_ROOT / thread_id / "files"
    host_path.mkdir(parents=True, exist_ok=True)
    entry = _create_sandbox_files_entry(str(host_path), name=f"sandbox-files-{thread_id}")
    return entry["sandbox_files_id"]


# ---------------------------------------------------------------------------
# Thread-scoped file operations
# ---------------------------------------------------------------------------


def _resolve_relative_path(base: Path, relative_path: str) -> Path:
    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError(f"Path must be relative: {relative_path}")
    candidate = (base / requested).resolve()
    # @@@path-boundary - Reject traversal so API callers cannot escape per-thread files root.
    candidate.relative_to(base.resolve())
    return candidate


def _get_sandbox_files_id(thread_id: str) -> str | None:
    """Look up sandbox_files_id from thread config."""
    from backend.web.utils.helpers import load_thread_config

    tc = load_thread_config(thread_id)
    return tc.get("sandbox_files_id") if tc else None


def _get_files_dir(thread_id: str, sandbox_files_id: str | None = None) -> Path:
    """Derive files directory. If sandbox_files_id not provided, look up from thread config."""
    if not sandbox_files_id:
        sandbox_files_id = _get_sandbox_files_id(thread_id)
    if not sandbox_files_id:
        raise ValueError(f"No sandbox files found for thread {thread_id}")

    entry = _get_sandbox_files_entry(sandbox_files_id)
    if not entry:
        raise ValueError(f"Sandbox files not found: {sandbox_files_id}")

    d = Path(entry["host_path"]).resolve()
    if not d.is_dir():
        raise ValueError(f"Sandbox files directory missing: {d}")
    return d


def ensure_sandbox_files(thread_id: str, sandbox_files_id: str | None = None) -> dict[str, Any]:
    """Ensure files directory exists. Returns channel info."""
    if not sandbox_files_id:
        sandbox_files_id = _get_sandbox_files_id(thread_id)
        if not sandbox_files_id:
            sandbox_files_id = create_sandbox_files(thread_id)
            from backend.web.utils.helpers import save_thread_config
            save_thread_config(thread_id, sandbox_files_id=sandbox_files_id)

    entry = _get_sandbox_files_entry(sandbox_files_id)
    if not entry:
        raise ValueError(f"Sandbox files not found: {sandbox_files_id}")

    files_dir = Path(entry["host_path"]).resolve()
    files_dir.mkdir(parents=True, exist_ok=True)
    return {
        "thread_id": thread_id,
        "sandbox_files_id": sandbox_files_id,
        "files_path": str(files_dir),
    }


def save_file(
    *,
    thread_id: str,
    relative_path: str,
    content: bytes,
    sandbox_files_id: str | None = None,
) -> dict[str, Any]:
    base = _get_files_dir(thread_id, sandbox_files_id)
    target = _resolve_relative_path(base, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()

    # @@@upload-touch-activity - File upload is user activity, update session timestamp to prevent idle reaper race
    from backend.web.services.activity_tracker import track_thread_activity
    track_thread_activity(thread_id, "file_upload")

    return {
        "thread_id": thread_id,
        "relative_path": str(Path(relative_path)),
        "absolute_path": str(target),
        "size_bytes": len(content),
        "sha256": digest,
    }


def resolve_file(
    *,
    thread_id: str,
    relative_path: str,
    sandbox_files_id: str | None = None,
) -> Path:
    base = _get_files_dir(thread_id, sandbox_files_id)
    target = _resolve_relative_path(base, relative_path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File not found: {relative_path}")
    return target


def list_files(
    *,
    thread_id: str,
    sandbox_files_id: str | None = None,
) -> list[dict[str, Any]]:
    base = _get_files_dir(thread_id, sandbox_files_id)
    entries: list[dict[str, Any]] = []
    for item in sorted(base.rglob("*")):
        if not item.is_file():
            continue
        entries.append(
            {
                "relative_path": str(item.relative_to(base)),
                "size_bytes": item.stat().st_size,
                "updated_at": datetime.fromtimestamp(item.stat().st_mtime, tz=UTC).isoformat(),
            }
        )
    return entries


def delete_file(
    *,
    thread_id: str,
    relative_path: str,
    sandbox_files_id: str | None = None,
) -> None:
    """Delete a file from sandbox files."""
    base = _get_files_dir(thread_id, sandbox_files_id)
    target = _resolve_relative_path(base, relative_path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File not found: {relative_path}")
    target.unlink()


def cleanup_sandbox_files(thread_id: str) -> None:
    """Delete disk files and sandbox files entity for a thread."""
    sandbox_files_id = _get_sandbox_files_id(thread_id)
    if sandbox_files_id:
        entry = _get_sandbox_files_entry(sandbox_files_id)
        # @@@safe-sandbox-files-delete - only delete auto-created sandbox-files entries, not shared ones
        if entry and (entry.get("name") or "").startswith(f"sandbox-files-{thread_id}"):
            _delete_sandbox_files_entry(sandbox_files_id)
    thread_root = (SANDBOX_FILES_ROOT / thread_id).resolve()
    if thread_root.exists():
        shutil.rmtree(thread_root)
