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
            profile_path = Path(
                os.getenv("MYCEL_AGENT_PROFILE_PATH") or Path.home() / ".config" / "mycel-agent" / "profiles.json"
            )
            payload = json.loads(profile_path.read_text(encoding="utf-8"))
            resolved_agent_user_id = str((payload.get("profiles") or {}).get(resolved_alias, {}).get("agent_user_id") or "").strip()
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
