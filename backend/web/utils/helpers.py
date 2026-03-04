"""General helper utilities."""

import re
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.web.core.config import DB_PATH
from storage.container import StorageContainer
from storage.contracts import ThreadConfigRepo
from storage.runtime import build_storage_container
from sandbox.db import DEFAULT_DB_PATH as SANDBOX_DB_PATH

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
    with sqlite3.connect(str(SANDBOX_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
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
    with sqlite3.connect(str(SANDBOX_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
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


def _ensure_thread_config_table(conn: sqlite3.Connection) -> None:
    """Create thread_config table and run migrations from old thread_metadata."""
    # Migrate old table name if exists
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "thread_metadata" in tables and "thread_config" not in tables:
        conn.execute("ALTER TABLE thread_metadata RENAME TO thread_config")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS thread_config"
        "(thread_id TEXT PRIMARY KEY, sandbox_type TEXT NOT NULL, cwd TEXT, model TEXT, queue_mode TEXT DEFAULT 'steer')"
    )
    for col, default in [
        ("model", None),
        ("queue_mode", "'steer'"),
        ("observation_provider", None),
        ("thread_mode", "'normal'"),
        ("keep_full_trace", "'0'"),
    ]:
        try:
            default_clause = f" DEFAULT {default}" if default else ""
            conn.execute(f"ALTER TABLE thread_config ADD COLUMN {col} TEXT{default_clause}")
        except sqlite3.OperationalError:
            pass


def save_thread_config(thread_id: str, **fields: Any) -> None:
    """Update specific fields of thread config in SQLite.

    Usage: save_thread_config(thread_id, model="gpt-4")
    """
    allowed = {
        "sandbox_type",
        "cwd",
        "model",
        "queue_mode",
        "observation_provider",
        "thread_mode",
        "keep_full_trace",
    }
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
    repo = _build_thread_config_repo()
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            _ensure_thread_config_table(conn)
            row = conn.execute(
                "SELECT sandbox_type, cwd, model, queue_mode, observation_provider, thread_mode, keep_full_trace "
                "FROM thread_config WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            if not row:
                return None
            from backend.web.models.thread_config import ThreadConfig

            return ThreadConfig(
                sandbox_type=row["sandbox_type"],
                cwd=row["cwd"],
                model=row["model"],
                queue_mode=row["queue_mode"] or "steer",
                observation_provider=row["observation_provider"],
                thread_mode=row["thread_mode"] or "normal",
                keep_full_trace=str(row["keep_full_trace"] or "0") in {"1", "true", "True"},
            )
    except sqlite3.OperationalError:
        return None


def init_thread_config(
    thread_id: str,
    sandbox_type: str,
    cwd: str | None,
    thread_mode: str = "normal",
    keep_full_trace: bool = False,
) -> None:
    """Create initial thread config row in SQLite."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        _ensure_thread_config_table(conn)
        conn.execute(
            "INSERT OR REPLACE INTO thread_config "
            "(thread_id, sandbox_type, cwd, thread_mode, keep_full_trace) "
            "VALUES (?, ?, ?, ?, ?)",
            (thread_id, sandbox_type, cwd, thread_mode, "1" if keep_full_trace else "0"),
        )
        conn.commit()


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


def lookup_thread_mode(thread_id: str) -> str:
    """Look up thread mode. Defaults to normal."""
    config = load_thread_config(thread_id)
    return config.thread_mode if config and config.thread_mode else "normal"


def should_keep_full_trace(thread_id: str) -> bool:
    """Whether thread run events should be fully retained."""
    config = load_thread_config(thread_id)
    return bool(config.keep_full_trace) if config else False


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
        with sqlite3.connect(str(SANDBOX_DB_PATH)) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            for table in tables:
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
                    continue
                cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
                if "thread_id" in cols:
                    conn.execute(f'DELETE FROM "{table}" WHERE thread_id = ?', (thread_id,))
            conn.commit()
