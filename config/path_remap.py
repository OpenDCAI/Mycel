from __future__ import annotations

import os
import sys
from pathlib import Path


def _default_home_dir() -> Path:
    return (Path.home() / ".leon").resolve()


def _explicit_db_parent() -> Path | None:
    if sys.platform != "win32":
        return None
    main_db = os.getenv("LEON_DB_PATH")
    if not main_db:
        return None
    return Path(main_db).expanduser().resolve().parent


def remap_default_home_string(value: str) -> str:
    expanded = os.path.expandvars(os.path.expanduser(value))
    preferred = _explicit_db_parent()
    if preferred is None:
        return expanded

    default_home = _default_home_dir()
    expanded_norm = expanded.replace("\\", "/")
    default_norm = str(default_home).replace("\\", "/")
    if expanded_norm == default_norm:
        return str(preferred)
    if expanded_norm.startswith(f"{default_norm}/"):
        relative = Path(expanded).relative_to(default_home)
        return str(preferred / relative)
    return expanded
