"""Profile CRUD — config.json based."""

import json
from pathlib import Path
from typing import Any

from config.user_paths import preferred_existing_user_home_path, user_home_path

LEON_HOME = user_home_path()
CONFIG_PATH = LEON_HOME / "config.json"


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_profile() -> dict[str, Any]:
    cfg = _read_json(preferred_existing_user_home_path("config.json"), {})
    profile = cfg.get("profile", {})
    return {
        "name": profile.get("name", "用户名"),
        "initials": profile.get("initials", "YZ"),
        "email": profile.get("email", "user@example.com"),
    }


def update_profile(**fields: Any) -> dict[str, Any]:
    allowed = {"name", "initials", "email"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_profile()
    cfg = _read_json(preferred_existing_user_home_path("config.json"), {})
    profile = cfg.get("profile", {})
    profile.update(updates)
    cfg["profile"] = profile
    _write_json(CONFIG_PATH, cfg)
    return get_profile()
