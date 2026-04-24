from __future__ import annotations

import re
import time
from typing import Any

import yaml


def _parse_agent_md_content(content: str) -> dict[str, Any] | None:
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    if not fm or "name" not in fm:
        return None
    return {
        "name": fm["name"],
        "description": fm.get("description", ""),
        "model": fm.get("model"),
        "tools": fm.get("tools", ["*"]),
        "system_prompt": parts[2].strip(),
    }


def _sanitize_name(name: str) -> str:
    sanitized = re.sub(r'[/\\<>:"|?*\x00-\x1f]', "_", name)
    sanitized = sanitized.strip(". ")
    if not sanitized:
        sanitized = "unnamed"
    return sanitized


def _save_config_to_repo(
    agent_config_repo: Any,
    agent_config_id: str,
    *,
    agent_user_id: str,
    owner_user_id: str,
    name: str,
    description: str = "",
    model: str | None = None,
    tools: list[str] | None = None,
    system_prompt: str = "",
    status: str = "draft",
    version: str = "0.1.0",
    created_at: int = 0,
    updated_at: int = 0,
    runtime: dict | None = None,
    mcp: dict | None = None,
    meta: dict | None = None,
) -> None:
    agent_config_repo.save_config(
        agent_config_id,
        {
            "agent_user_id": agent_user_id,
            "owner_user_id": owner_user_id,
            "name": name,
            "description": description,
            "model": model,
            "tools": tools or ["*"],
            "system_prompt": system_prompt,
            "status": status,
            "version": version,
            "created_at": created_at,
            "updated_at": updated_at,
            "runtime": runtime or {},
            "mcp": mcp or {},
            "meta": meta or {},
        },
    )


def install_from_snapshot(
    snapshot: dict,
    name: str,
    description: str,
    marketplace_item_id: str,
    installed_version: str,
    owner_user_id: str,
    existing_user_id: str | None = None,
    user_repo: Any = None,
    agent_config_repo: Any = None,
) -> str:
    """Create or update a marketplace-backed agent user via repos only."""
    from storage.contracts import UserRow, UserType
    from storage.utils import generate_agent_config_id, generate_agent_user_id

    if user_repo is None or agent_config_repo is None:
        raise RuntimeError("user_repo and agent_config_repo are required to install marketplace user snapshot")

    now = time.time()
    now_ms = int(now * 1000)
    agent_md = _parse_agent_md_content(str(snapshot.get("agent_md") or "")) or {}
    agent_name = str(agent_md.get("name") or name)
    agent_description = str(agent_md.get("description") or description)
    agent_model = agent_md.get("model")
    agent_tools = list(agent_md.get("tools") or ["*"])
    agent_prompt = str(agent_md.get("system_prompt") or "")
    runtime_data = snapshot.get("runtime") if isinstance(snapshot.get("runtime"), dict) else {}
    mcp_data = snapshot.get("mcp") if isinstance(snapshot.get("mcp"), dict) else {}

    if existing_user_id:
        user_id = existing_user_id
        user = user_repo.get_by_id(user_id)
        if user is None or user.agent_config_id is None:
            raise RuntimeError(f"Agent user {user_id} is missing agent_config_id")
        agent_config_id = user.agent_config_id
        current_config = agent_config_repo.get_config(agent_config_id)
        if current_config is None:
            raise RuntimeError(f"Agent config {agent_config_id} is missing for {user_id}")
        created_at = int(current_config.get("created_at", now_ms))
        user_repo.update(user_id, display_name=agent_name)
    else:
        user_id = generate_agent_user_id()
        agent_config_id = generate_agent_config_id()
        created_at = now_ms
        row = UserRow(
            id=user_id,
            type=UserType.AGENT,
            display_name=agent_name,
            owner_user_id=owner_user_id,
            agent_config_id=agent_config_id,
            created_at=now,
        )
        user_repo.create(row)

    _save_config_to_repo(
        agent_config_repo,
        agent_config_id,
        agent_user_id=user_id,
        owner_user_id=owner_user_id,
        name=agent_name,
        description=agent_description,
        model=agent_model,
        tools=agent_tools,
        system_prompt=agent_prompt,
        status="active",
        version=installed_version,
        created_at=created_at,
        updated_at=now_ms,
        runtime=runtime_data,
        mcp=mcp_data,
        meta={
            "source": {
                "marketplace_item_id": marketplace_item_id,
                "installed_version": installed_version,
                "installed_at": now_ms,
                "modified": False,
            }
        },
    )

    for row in agent_config_repo.list_rules(agent_config_id):
        agent_config_repo.delete_rule(row["id"])
    for rule in snapshot.get("rules", []):
        if not isinstance(rule, dict):
            continue
        rule_name = _sanitize_name(str(rule.get("name") or "default"))
        agent_config_repo.save_rule(agent_config_id, f"{rule_name}.md", str(rule.get("content") or ""))

    for row in agent_config_repo.list_skills(agent_config_id):
        agent_config_repo.delete_skill(row["id"])
    for skill in snapshot.get("skills", []):
        if not isinstance(skill, dict):
            continue
        skill_name = _sanitize_name(str(skill.get("name") or "default"))
        skill_meta = dict(skill.get("meta")) if isinstance(skill.get("meta"), dict) else {}
        if skill.get("desc") is not None:
            skill_meta["desc"] = str(skill.get("desc") or "")
        agent_config_repo.save_skill(agent_config_id, skill_name, str(skill.get("content") or ""), meta=skill_meta)

    for row in agent_config_repo.list_sub_agents(agent_config_id):
        agent_config_repo.delete_sub_agent(row["id"])
    for item in snapshot.get("agents", []):
        if not isinstance(item, dict):
            continue
        parsed_sub_agent = _parse_agent_md_content(str(item.get("content") or "")) or {}
        sub_agent_name = str(parsed_sub_agent.get("name") or item.get("name") or "default")
        agent_config_repo.save_sub_agent(
            agent_config_id,
            _sanitize_name(sub_agent_name),
            description=str(parsed_sub_agent.get("description") or ""),
            model=parsed_sub_agent.get("model"),
            tools=list(parsed_sub_agent.get("tools") or ["*"]),
            system_prompt=str(parsed_sub_agent.get("system_prompt") or ""),
        )

    return user_id
