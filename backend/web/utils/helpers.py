"""General helper utilities."""

import re
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.web.core.config import DB_PATH
from storage.container import StorageContainer
from storage.providers.sqlite.kernel import connect_sqlite
from storage.runtime import build_storage_container
from sandbox.config import DEFAULT_DB_PATH as SANDBOX_DB_PATH

# @@@cached-container - reuse a single StorageContainer across helper calls to avoid per-call rebuild.
_cached_container: StorageContainer | None = None
_cached_container_db_path: Path | None = None


def is_virtual_thread_id(thread_id: str | None) -> bool:
    """Check if thread_id is a virtual thread (wrapped in parentheses)."""
    return bool(thread_id) and thread_id.startswith("(") and thread_id.endswith(")")


def get_terminal_timestamps(terminal_id: str) -> tuple[str | None, str | None]:
    """Get created_at and updated_at timestamps for a terminal."""
    if not SANDBOX_DB_PATH.exists():
        return None, None
    with connect_sqlite(SANDBOX_DB_PATH, row_factory=sqlite3.Row) as conn:
        row = conn.execute(
            "SELECT created_at, updated_at FROM abstract_terminals WHERE terminal_id = ?",
            (terminal_id,),
        ).fetchone()
        if not row:
            return None, None
        return row["created_at"], row["updated_at"]


def get_lease_timestamps(lease_id: str) -> tuple[str | None, str | None]:
    """Get created_at and updated_at timestamps for a lease."""
    if not SANDBOX_DB_PATH.exists():
        return None, None
    with connect_sqlite(SANDBOX_DB_PATH, row_factory=sqlite3.Row) as conn:
        row = conn.execute(
            "SELECT created_at, updated_at FROM sandbox_leases WHERE lease_id = ?",
            (lease_id,),
        ).fetchone()
        if not row:
            return None, None
        return row["created_at"], row["updated_at"]


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
    global _cached_container, _cached_container_db_path
    if _cached_container is not None and _cached_container_db_path == DB_PATH:
        return _cached_container
    _cached_container = build_storage_container(main_db_path=DB_PATH)
    _cached_container_db_path = DB_PATH
    return _cached_container


def get_active_observation_provider() -> str | None:
    """Read global observation config and return the active provider name."""
    from config.observation_loader import ObservationLoader

    config = ObservationLoader().load()
    return config.active if config.active else None


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

    # Use thread-specific workspace root if available from memory cache
    thread_cwd = None
    if thread_id:
        if thread_cwd_map:
            thread_cwd = thread_cwd_map.get(thread_id)
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

    # Purge sandbox db tables (not managed by storage repos)
    if SANDBOX_DB_PATH.exists():
        with connect_sqlite(SANDBOX_DB_PATH) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            for table in tables:
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
                    continue
                cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
                if "thread_id" in cols:
                    conn.execute(f'DELETE FROM "{table}" WHERE thread_id = ?', (thread_id,))
            conn.commit()
