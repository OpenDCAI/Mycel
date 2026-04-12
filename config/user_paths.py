from __future__ import annotations

import os
import sys
from pathlib import Path


def default_user_home_dir() -> Path:
    return (Path.home() / ".leon").resolve()


def preferred_user_home_dir() -> Path:
    if sys.platform == "win32":
        main_db = os.getenv("LEON_DB_PATH")
        if main_db:
            return Path(main_db).expanduser().resolve().parent
    return default_user_home_dir()


def user_home_read_roots() -> tuple[Path, ...]:
    preferred = preferred_user_home_dir()
    default_home = default_user_home_dir()
    if preferred == default_home:
        return (preferred,)
    return (default_home, preferred)


def user_home_path(*parts: str) -> Path:
    return preferred_user_home_dir().joinpath(*parts)


def user_home_read_candidates(*parts: str) -> tuple[Path, ...]:
    return tuple(root.joinpath(*parts) for root in user_home_read_roots())


def first_existing_user_home_path(*parts: str) -> Path:
    for path in user_home_read_candidates(*parts):
        if path.exists():
            return path
    return user_home_path(*parts)


def preferred_existing_user_home_path(*parts: str) -> Path:
    preferred = user_home_path(*parts)
    if preferred.exists():
        return preferred
    for path in user_home_read_candidates(*parts):
        if path == preferred:
            continue
        if path.exists():
            return path
    return preferred


def remap_default_user_home_string(value: str) -> str:
    expanded = os.path.expandvars(os.path.expanduser(value))
    preferred = preferred_user_home_dir()
    default_home = default_user_home_dir()
    if preferred == default_home:
        return expanded

    expanded_norm = expanded.replace("\\", "/")
    default_norm = str(default_home).replace("\\", "/")
    if expanded_norm == default_norm:
        return str(preferred)
    if expanded_norm.startswith(f"{default_norm}/"):
        relative = Path(expanded).relative_to(default_home)
        return str(preferred / relative)
    return expanded
