"""Shared local workspace root helper."""

from __future__ import annotations

import os
from pathlib import Path


def local_workspace_root() -> Path:
    return Path(os.environ.get("LEON_LOCAL_WORKSPACE_ROOT", str(Path.home()))).expanduser().resolve()
