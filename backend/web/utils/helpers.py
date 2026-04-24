from pathlib import Path
from typing import Any

from fastapi import HTTPException

from storage.runtime import (
    build_thread_repo,
)

_cached_thread_repo = None


def load_thread_row(thread_id: str, thread_repo=None) -> dict[str, Any] | None:
    if thread_repo is None:
        global _cached_thread_repo
        if _cached_thread_repo is None:
            _cached_thread_repo = build_thread_repo()
        thread_repo = _cached_thread_repo
    return thread_repo.get_by_id(thread_id)


def resolve_local_workspace_path(
    raw_path: str | None,
    thread_id: str | None = None,
    thread_cwd_map: dict[str, str] | None = None,
    local_workspace_root: Path | None = None,
) -> Path:
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
