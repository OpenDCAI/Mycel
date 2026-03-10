"""Workspace and thread-scoped file service.

A workspace is a named directory on the host machine that can be shared across
multiple threads. Each thread can have at most one workspace_id; multiple threads
can reference the same workspace.

Files path is derived, not cached in DB:
  - thread has workspace_id → workspace.host_path
  - otherwise → THREAD_FILES_ROOT / thread_id / files
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

from backend.web.core.config import THREAD_FILES_ROOT
from backend.web.utils.helpers import _get_container
from storage.contracts import WorkspaceRepo


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _repo() -> WorkspaceRepo:
    return _get_container().workspace_repo()


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------


def _create_workspace(host_path: str, name: str | None = None) -> dict[str, Any]:
    """Internal: Create workspace entity. Used by thread operations only."""
    host = Path(host_path).expanduser().resolve()
    if not host.exists():
        raise ValueError(f"Workspace host_path does not exist: {host}")
    workspace_id = str(uuid.uuid4())
    now = _now_utc()
    repo = _repo()
    try:
        repo.create(workspace_id, str(host), name, now)
    finally:
        repo.close()
    return {"workspace_id": workspace_id, "host_path": str(host), "name": name, "created_at": now}


def _get_workspace(workspace_id: str) -> dict[str, Any] | None:
    """Internal: Lookup workspace entity."""
    repo = _repo()
    try:
        return repo.get(workspace_id)
    finally:
        repo.close()


def _list_workspaces() -> list[dict[str, Any]]:
    """Internal: List all workspace entities."""
    repo = _repo()
    try:
        return repo.list_all()
    finally:
        repo.close()


def _delete_workspace(workspace_id: str) -> bool:
    """Internal: Delete workspace entity (does not remove host directory)."""
    repo = _repo()
    try:
        return repo.delete(workspace_id)
    finally:
        repo.close()


def create_file_channel_workspace(thread_id: str) -> str:
    """Create file channel workspace for thread. Returns workspace_id."""
    host_path = THREAD_FILES_ROOT / thread_id / "files"
    host_path.mkdir(parents=True, exist_ok=True)
    ws = _create_workspace(str(host_path), name=f"file-channel-{thread_id}")
    return ws["workspace_id"]


# ---------------------------------------------------------------------------
# Thread-scoped file operations (merged from file_channel_service)
# ---------------------------------------------------------------------------


def _resolve_relative_path(base: Path, relative_path: str) -> Path:
    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError(f"Path must be relative: {relative_path}")
    candidate = (base / requested).resolve()
    # @@@path-boundary - Reject traversal so API callers cannot escape per-thread files root.
    candidate.relative_to(base.resolve())
    return candidate


def _get_workspace_id(thread_id: str) -> str | None:
    """Look up workspace_id from thread config."""
    from backend.web.utils.helpers import load_thread_config

    tc = load_thread_config(thread_id)
    return tc.workspace_id if tc else None


def _get_files_dir(thread_id: str, workspace_id: str | None = None) -> Path:
    """Derive files directory. If workspace_id not provided, use thread's file channel workspace."""
    if not workspace_id:
        workspace_id = _get_workspace_id(thread_id)
    if not workspace_id:
        raise ValueError(f"No workspace found for thread {thread_id}")

    ws = _get_workspace(workspace_id)
    if not ws:
        raise ValueError(f"Workspace not found: {workspace_id}")

    d = Path(ws["host_path"]).resolve()
    if not d.is_dir():
        raise ValueError(f"Workspace directory missing: {d}")
    return d


def ensure_thread_files(thread_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    """Ensure files directory exists. Returns channel info."""
    # If no workspace_id provided, check thread config or create file channel workspace
    if not workspace_id:
        workspace_id = _get_workspace_id(thread_id)
        if not workspace_id:
            workspace_id = create_file_channel_workspace(thread_id)
            # Save to thread config
            from backend.web.utils.helpers import save_thread_config
            save_thread_config(thread_id, workspace_id=workspace_id)

    ws = _get_workspace(workspace_id)
    if not ws:
        raise ValueError(f"Workspace not found: {workspace_id}")

    files_dir = Path(ws["host_path"]).resolve()
    files_dir.mkdir(parents=True, exist_ok=True)
    return {
        "thread_id": thread_id,
        "workspace_id": workspace_id,
        "files_path": str(files_dir),
    }


def save_file(
    *,
    thread_id: str,
    relative_path: str,
    content: bytes,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    base = _get_files_dir(thread_id, workspace_id)
    target = _resolve_relative_path(base, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
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
    workspace_id: str | None = None,
) -> Path:
    base = _get_files_dir(thread_id, workspace_id)
    target = _resolve_relative_path(base, relative_path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File not found: {relative_path}")
    return target


def list_files(
    *,
    thread_id: str,
    workspace_id: str | None = None,
) -> list[dict[str, Any]]:
    base = _get_files_dir(thread_id, workspace_id)
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
    workspace_id: str | None = None,
) -> None:
    """Delete a file from workspace."""
    base = _get_files_dir(thread_id, workspace_id)
    target = _resolve_relative_path(base, relative_path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File not found: {relative_path}")
    target.unlink()


# ---------------------------------------------------------------------------
# Agent Workplace operations
# ---------------------------------------------------------------------------


def _workplace_repo():
    return _get_container().workplace_repo()


def get_agent_workplace(member_name: str, provider_type: str) -> dict[str, Any] | None:
    repo = _workplace_repo()
    try:
        return repo.get(member_name, provider_type)
    finally:
        repo.close()


def create_agent_workplace(
    member_name: str, provider_type: str, backend_ref: str, mount_path: str,
) -> dict[str, Any]:
    now = _now_utc()
    repo = _workplace_repo()
    try:
        repo.upsert(member_name, provider_type, backend_ref, mount_path, now)
    finally:
        repo.close()
    logger.info("Created workplace: member=%s provider=%s ref=%s", member_name, provider_type, backend_ref)
    return {
        "member_name": member_name, "provider_type": provider_type,
        "backend_ref": backend_ref, "mount_path": mount_path, "created_at": now,
    }


def list_agent_workplaces(member_name: str) -> list[dict[str, Any]]:
    repo = _workplace_repo()
    try:
        return repo.list_by_member(member_name)
    finally:
        repo.close()


def delete_all_agent_workplaces(member_name: str) -> int:
    repo = _workplace_repo()
    try:
        count = repo.delete_all_for_member(member_name)
    finally:
        repo.close()
    if count:
        logger.info("Deleted %d workplace(s) for member=%s", count, member_name)
    return count


def cleanup_thread_files(thread_id: str) -> None:
    """Delete disk files and workspace entity for a thread."""
    workspace_id = _get_workspace_id(thread_id)
    if workspace_id:
        ws = _get_workspace(workspace_id)
        # @@@safe-workspace-delete - only delete auto-created file-channel workspaces, not shared ones
        if ws and (ws.get("name") or "").startswith(f"file-channel-{thread_id}"):
            _delete_workspace(workspace_id)
    thread_root = (THREAD_FILES_ROOT / thread_id).resolve()
    if thread_root.exists():
        shutil.rmtree(thread_root)
