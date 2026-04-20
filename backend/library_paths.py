"""Shared library path owner."""

from __future__ import annotations

from pathlib import Path

from config.user_paths import preferred_user_home_dir


def leon_home_dir() -> Path:
    return preferred_user_home_dir()


def library_dir() -> Path:
    return leon_home_dir() / "library"


LIBRARY_DIR = library_dir()
