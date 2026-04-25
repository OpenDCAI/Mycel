"""Apply Hub AgentSnapshot payloads into AgentConfig aggregates."""

from __future__ import annotations

import time
from typing import Any

from config.agent_config_types import AgentConfig, AgentSnapshot


def apply_snapshot(
    *,
    snapshot: dict,
    marketplace_item_id: str,
    source_version: str,
    owner_user_id: str,
    existing_user_id: str | None = None,
    user_repo: Any = None,
    agent_config_repo: Any = None,
) -> str:
    from storage.contracts import UserRow, UserType
    from storage.utils import generate_agent_config_id, generate_agent_user_id

    if user_repo is None or agent_config_repo is None:
        raise RuntimeError("user_repo and agent_config_repo are required to apply marketplace user snapshot")

    parsed = AgentSnapshot.model_validate(snapshot)
    resolved = parsed.agent
    now = time.time()

    if existing_user_id:
        user_id = existing_user_id
        user = user_repo.get_by_id(user_id)
        if user is None or user.agent_config_id is None:
            raise RuntimeError(f"Agent user {user_id} is missing agent_config_id")
        agent_config_id = user.agent_config_id
        user_repo.update(user_id, display_name=resolved.name)
    else:
        user_id = generate_agent_user_id()
        agent_config_id = generate_agent_config_id()
        user_repo.create(
            UserRow(
                id=user_id,
                type=UserType.AGENT,
                display_name=resolved.name,
                owner_user_id=owner_user_id,
                agent_config_id=agent_config_id,
                created_at=now,
            )
        )

    meta = dict(resolved.meta)
    meta["source"] = {
        "marketplace_item_id": marketplace_item_id,
        "source_version": source_version,
        "source_at": int(now * 1000),
        "modified": False,
    }

    agent_config_repo.save_agent_config(
        AgentConfig(
            id=agent_config_id,
            owner_user_id=owner_user_id,
            agent_user_id=user_id,
            name=resolved.name,
            description=resolved.description,
            model=resolved.model,
            tools=resolved.tools,
            system_prompt=resolved.system_prompt,
            status="active",
            version=source_version,
            runtime_settings=resolved.runtime_settings,
            compact=resolved.compact,
            skills=resolved.skills,
            rules=resolved.rules,
            sub_agents=resolved.sub_agents,
            mcp_servers=resolved.mcp_servers,
            meta=meta,
        )
    )
    return user_id
