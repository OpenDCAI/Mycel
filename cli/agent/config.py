"""Configuration loading for the Stage-1 agent CLI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentCliConfig:
    agent_user_id: str
    chat_base_url: str
    threads_base_url: str


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
    agent_user_id: str,
    chat_base_url: str,
    threads_base_url: str,
) -> dict[str, str]:
    profiles = load_profiles()
    profiles[name] = {
        "agent_user_id": agent_user_id,
        "chat_base_url": chat_base_url,
        "threads_base_url": threads_base_url,
    }
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"profiles": profiles}, ensure_ascii=False, indent=2), encoding="utf-8")
    return profiles[name]


def load_cli_config(
    *,
    agent_user_id: str | None,
    agent_alias: str | None = None,
    chat_base_url: str | None,
    threads_base_url: str | None,
) -> AgentCliConfig:
    resolved_agent_user_id = str(agent_user_id or os.getenv("MYCEL_AGENT_USER_ID") or "").strip()
    if not resolved_agent_user_id:
        resolved_alias = str(agent_alias or os.getenv("MYCEL_AGENT_ALIAS") or "").strip()
        if resolved_alias:
            resolved_agent_user_id = str(load_profiles().get(resolved_alias, {}).get("agent_user_id") or "").strip()
    if not resolved_agent_user_id:
        raise RuntimeError("MYCEL_AGENT_USER_ID is required")

    resolved_chat_base_url = str(chat_base_url or os.getenv("MYCEL_CHAT_BACKEND_URL") or "http://127.0.0.1:8013").strip()
    resolved_threads_base_url = str(
        threads_base_url or os.getenv("MYCEL_THREADS_BACKEND_URL") or "http://127.0.0.1:8012"
    ).strip()

    return AgentCliConfig(
        agent_user_id=resolved_agent_user_id,
        chat_base_url=resolved_chat_base_url,
        threads_base_url=resolved_threads_base_url,
    )
