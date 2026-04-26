from __future__ import annotations

import os
from pathlib import Path


def local_workspace_root() -> Path:
    raw_path = os.environ.get("LEON_LOCAL_WORKSPACE_ROOT")
    if not raw_path:
        raise RuntimeError("LEON_LOCAL_WORKSPACE_ROOT is required for local workspace access.")
    return Path(raw_path).expanduser().resolve()
