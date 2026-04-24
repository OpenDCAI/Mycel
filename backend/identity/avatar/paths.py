from __future__ import annotations

from pathlib import Path

from config.user_paths import preferred_user_home_dir


def avatars_dir() -> Path:
    return preferred_user_home_dir() / "avatars"
