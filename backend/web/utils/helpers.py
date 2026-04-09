"""General helper utilities."""

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from sandbox.control_plane_repos import resolve_sandbox_db_path
from sandbox.sync.state import SyncState
from storage.container import StorageContainer
from storage.runtime import build_chat_session_repo as make_chat_session_repo
from storage.runtime import build_lease_repo as make_lease_repo
from storage.runtime import build_storage_container, build_thread_repo
from storage.runtime import build_terminal_repo as make_terminal_repo

_cached_container: StorageContainer | None = None


def is_virtual_thread_id(thread_id: str | None) -> bool:
    """Check if thread_id is a virtual thread (wrapped in parentheses)."""
    return bool(thread_id) and thread_id.startswith("(") and thread_id.endswith(")")


def get_terminal_timestamps(terminal_id: str) -> tuple[str | None, str | None]:
    """Get created_at and updated_at timestamps for a terminal."""
    sandbox_db = resolve_sandbox_db_path()
    if not sandbox_db.exists():
        return None, None
    repo = make_terminal_repo(db_path=sandbox_db)
    try:
        return repo.get_timestamps(terminal_id)
    finally:
        repo.close()


def get_lease_timestamps(lease_id: str) -> tuple[str | None, str | None]:
    """Get created_at and updated_at timestamps for a lease."""
    sandbox_db = resolve_sandbox_db_path()
    if not sandbox_db.exists():
        return None, None
    repo = make_lease_repo(db_path=sandbox_db)
    try:
        row = repo.get(lease_id)
    finally:
        repo.close()
    if row is None:
        return None, None
    return str(row.get("created_at") or "") or None, str(row.get("updated_at") or "") or None


def extract_webhook_instance_id(payload: dict[str, Any]) -> str | None:
    """Extract provider instance/session id from webhook payload."""
    direct_keys = ("session_id", "sandbox_id", "instance_id", "id")
    for key in direct_keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value

    nested = payload.get("data")
    if isinstance(nested, dict):
        for key in direct_keys:
            value = nested.get(key)
            if isinstance(value, str) and value:
                return value

    return None


def _get_container() -> StorageContainer:
    global _cached_container
    if _cached_container is not None:
        return _cached_container
    _cached_container = build_storage_container()
    return _cached_container


_cached_thread_repo = None


def _get_thread_repo(thread_repo=None):
    """Get cached ThreadRepo instance, or use injected repo."""
    if thread_repo is not None:
        return thread_repo
    global _cached_thread_repo
    if _cached_thread_repo is not None:
        return _cached_thread_repo
    _cached_thread_repo = build_thread_repo()
    return _cached_thread_repo


def load_thread_config(thread_id: str, thread_repo=None) -> dict[str, Any] | None:
    """Load thread data. Returns dict or None."""
    return _get_thread_repo(thread_repo).get_by_id(thread_id)


def resolve_local_workspace_path(
    raw_path: str | None,
    thread_id: str | None = None,
    thread_cwd_map: dict[str, str] | None = None,
    local_workspace_root: Path | None = None,
) -> Path:
    """Resolve a workspace path relative to thread-specific or global workspace root."""
    from backend.web.core.config import LOCAL_WORKSPACE_ROOT

    if local_workspace_root is None:
        local_workspace_root = LOCAL_WORKSPACE_ROOT

    # Use thread-specific workspace root if available (memory → SQLite fallback)
    thread_cwd = None
    if thread_id:
        if thread_cwd_map:
            thread_cwd = thread_cwd_map.get(thread_id)
        if not thread_cwd:
            tc = load_thread_config(thread_id)
            if tc:
                thread_cwd = tc.get("cwd")
    # @@@workspace-base-normalize - relative LOCAL_WORKSPACE_ROOT must be normalized, or target.relative_to(base) always fails.
    base = Path(thread_cwd).resolve() if thread_cwd else local_workspace_root.resolve()

    if not raw_path:
        return base
    requested = Path(raw_path).expanduser()
    if requested.is_absolute():
        target = requested.resolve()
    else:
        target = (base / requested).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(400, f"Path outside workspace: {target}") from exc
    return target


def delete_thread_in_db(thread_id: str) -> None:
    """Delete all records for a thread via storage repos + sandbox db."""
    # Purge storage-managed repos (works for both sqlite and supabase strategies)
    _get_container().purge_thread(thread_id)

    sandbox_db = resolve_sandbox_db_path()
    if not sandbox_db.exists():
        return

    session_repo = make_chat_session_repo(db_path=sandbox_db)
    terminal_repo = make_terminal_repo(db_path=sandbox_db)
    sync_state = SyncState()
    try:
        session_repo.delete_by_thread(thread_id)
        terminal_repo.delete_by_thread(thread_id)
        sync_state.clear_thread(thread_id)
    finally:
        sync_state.close()
        session_repo.close()
        terminal_repo.close()
