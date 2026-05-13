from __future__ import annotations

from pathlib import Path

from backend.sandboxes.local_workspace import local_workspace_root as resolve_local_workspace_root


def local_workspace_root() -> Path:
    return resolve_local_workspace_root()
