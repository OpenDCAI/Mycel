"""Monitor-local access to app config values."""

from __future__ import annotations

from pathlib import Path

from backend.local_workspace import local_workspace_root as resolve_local_workspace_root


def local_workspace_root() -> Path:
    return resolve_local_workspace_root()
