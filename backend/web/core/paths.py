"""Web runtime path helpers."""

from __future__ import annotations

from pathlib import Path

from config.user_paths import preferred_user_home_dir


def leon_home_dir() -> Path:
    """Return the filesystem root for Leon web runtime assets."""
    return preferred_user_home_dir()


def library_dir() -> Path:
    return leon_home_dir() / "library"


def avatars_dir() -> Path:
    return leon_home_dir() / "avatars"
