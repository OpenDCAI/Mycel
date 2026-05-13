from __future__ import annotations

import os
from pathlib import Path


def avatars_dir() -> Path:
    root = os.environ.get("LEON_AVATAR_ROOT")
    if not root:
        raise RuntimeError("LEON_AVATAR_ROOT is required for avatar storage")
    return Path(root).expanduser().resolve()
