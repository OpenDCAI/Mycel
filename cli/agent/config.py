"""Configuration loading for the Stage-1 agent CLI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CHAT_BASE_URL = "http://127.0.0.1:8013"
DEFAULT_THREADS_BASE_URL = "http://127.0.0.1:8012"
DEFAULT_APP_BASE_URL = "http://127.0.0.1:8010"


@dataclass(frozen=True)
class AgentCliConfig:
    agent_user_id: str | None
    chat_base_url: str
    threads_base_url: str
    app_base_url: str
    auth_token: str | None


def profile_path() -> Path:
    return Path(os.getenv("MYCEL_AGENT_PROFILE_PATH") or Path.home() / ".config" / "mycel-agent" / "profiles.json")


def load_profiles() -> dict[str, dict[str, str]]:
    path = profile_path()
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload.get("profiles") or {})


def save_profile(
    *,
    name: str,
    agent_user_id: str | None,
    chat_base_url: str,
    threads_base_url: str,
    app_base_url: str | None,
    auth_token: str | None,
) -> dict[str, str]:
    profiles = load_profiles()
    profile: dict[str, str] = {
        "chat_base_url": chat_base_url,
        "threads_base_url": threads_base_url,
    }
    if app_base_url:
        profile["app_base_url"] = app_base_url
    if agent_user_id:
        profile["agent_user_id"] = agent_user_id
    if auth_token:
        profile["auth_token"] = auth_token
    profiles[name] = profile
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"profiles": profiles}, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def load_cli_config(
    *,
    agent_user_id: str | None,
    agent_alias: str | None = None,
    chat_base_url: str | None,
    threads_base_url: str | None,
    app_base_url: str | None = None,
    auth_token: str | None = None,
    require_agent_user_id: bool = True,
) -> AgentCliConfig:
    resolved_alias = str(agent_alias or os.getenv("MYCEL_AGENT_ALIAS") or "").strip()
    profile = load_profiles().get(resolved_alias, {}) if resolved_alias else {}

    resolved_agent_user_id = str(agent_user_id or os.getenv("MYCEL_AGENT_USER_ID") or profile.get("agent_user_id") or "").strip()
    if require_agent_user_id and not resolved_agent_user_id:
        raise RuntimeError("MYCEL_AGENT_USER_ID is required")

    resolved_chat_base_url = str(
        chat_base_url or os.getenv("MYCEL_CHAT_BACKEND_URL") or profile.get("chat_base_url") or DEFAULT_CHAT_BASE_URL
    ).strip()
    resolved_threads_base_url = str(
        threads_base_url
        or os.getenv("MYCEL_THREADS_BACKEND_URL")
        or profile.get("threads_base_url")
        or DEFAULT_THREADS_BASE_URL
    ).strip()
    resolved_app_base_url = str(
        app_base_url or os.getenv("MYCEL_APP_BACKEND_URL") or profile.get("app_base_url") or DEFAULT_APP_BASE_URL
    ).strip()
    resolved_auth_token = str(auth_token or os.getenv("MYCEL_AGENT_AUTH_TOKEN") or profile.get("auth_token") or "").strip() or None

    return AgentCliConfig(
        agent_user_id=resolved_agent_user_id or None,
        chat_base_url=resolved_chat_base_url,
        threads_base_url=resolved_threads_base_url,
        app_base_url=resolved_app_base_url,
        auth_token=resolved_auth_token,
    )
