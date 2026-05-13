from __future__ import annotations

import os
from pathlib import Path


def file_channel_root(workspace_id: str) -> Path:
    root = os.environ.get("LEON_FILE_CHANNEL_ROOT")
    if not root:
        raise RuntimeError("LEON_FILE_CHANNEL_ROOT is required for file channel storage")
    workspace_key = str(workspace_id).strip()
    if not workspace_key:
        raise ValueError("workspace_id is required")
    return (Path(root).expanduser().resolve() / workspace_key).resolve()
