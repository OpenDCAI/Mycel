"""General helper utilities."""

import re
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.web.core.config import DB_PATH
from storage.container import StorageContainer
from storage.contracts import ThreadConfigRepo
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


def _build_thread_config_repo() -> ThreadConfigRepo:
    return _get_container().thread_config_repo()


def save_thread_config(thread_id: str, **fields: Any) -> None:
    """Update specific fields of thread config in SQLite.

    Usage: save_thread_config(thread_id, model="gpt-4")
    """
    import json as _json

    allowed = {"sandbox_type", "cwd", "model", "queue_mode", "observation_provider", "agent", "bind_mounts_json"}
    # @@@bind-mounts-json-serialize - convert bind_mounts list to JSON string for storage
    if "bind_mounts" in fields:
        raw = fields.pop("bind_mounts")
        if raw:
            fields["bind_mounts_json"] = _json.dumps([m.model_dump() if hasattr(m, "model_dump") else m for m in raw])
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    repo = _build_thread_config_repo()
    try:
        repo.update_fields(thread_id, **updates)
    finally:
        repo.close()


def load_thread_config(thread_id: str):
    """Load full thread config from SQLite. Returns ThreadConfig or None."""
    import json as _json

    repo = _build_thread_config_repo()
    try:
        row = repo.lookup_config(thread_id)
        if not row:
            return None
        from backend.web.models.thread_config import ThreadConfig

        bind_mounts_raw = row.get("bind_mounts_json")
        bind_mounts = _json.loads(bind_mounts_raw) if bind_mounts_raw else []

        return ThreadConfig(
            sandbox_type=row["sandbox_type"] or "local",
            cwd=row["cwd"],
            model=row["model"],
            queue_mode=row["queue_mode"] or "steer",
            observation_provider=row["observation_provider"],
            agent=row.get("agent"),
            bind_mounts=bind_mounts,
        )
    finally:
        repo.close()


def init_thread_config(thread_id: str, sandbox_type: str, cwd: str | None) -> None:
    """Create initial thread config row in storage repo."""
    repo = _build_thread_config_repo()
    try:
        repo.save_metadata(thread_id, sandbox_type, cwd)
    finally:
        repo.close()


def get_active_observation_provider() -> str | None:
    """Read global observation config and return the active provider name."""
    from config.observation_loader import ObservationLoader

    config = ObservationLoader().load()
    return config.active if config.active else None


def save_thread_model(thread_id: str, model: str) -> None:
    """Persist the selected model for a thread."""
    repo = _build_thread_config_repo()
    try:
        repo.save_model(thread_id, model)
    finally:
        repo.close()


def lookup_thread_model(thread_id: str) -> str | None:
    """Look up persisted model for a thread."""
    repo = _build_thread_config_repo()
    try:
        return repo.lookup_model(thread_id)
    finally:
        repo.close()


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
                thread_cwd = tc.cwd
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
