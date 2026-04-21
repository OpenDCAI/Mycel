"""General helper utilities."""

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from storage.runtime import (
    build_thread_repo,
)


def is_virtual_thread_id(thread_id: str | None) -> bool:
    """Check if thread_id is a virtual thread (wrapped in parentheses)."""
    return bool(thread_id) and thread_id.startswith("(") and thread_id.endswith(")")


def extract_webhook_instance_id(payload: dict[str, Any]) -> str | None:
    """Extract provider lower-runtime id from webhook payload."""
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


def load_thread_row(thread_id: str, thread_repo=None) -> dict[str, Any] | None:
    """Load the current thread row. Returns dict or None."""
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

    # Use thread-specific workspace root if available (live map → persisted thread config).
    thread_cwd = None
    if thread_id:
        if thread_cwd_map:
            thread_cwd = thread_cwd_map.get(thread_id)
        if not thread_cwd:
            tc = load_thread_row(thread_id)
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
