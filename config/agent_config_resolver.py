from __future__ import annotations

from typing import Any

from config.agent_config_types import AgentConfig, AgentSkill, ResolvedAgentConfig, ResolvedSkill
from config.skill_document import parse_skill_document


def resolve_agent_config(config: AgentConfig, *, skill_repo: Any = None) -> ResolvedAgentConfig:
    resolved_skills = []
    seen_skill_names: set[str] = set()
    for skill in config.skills:
        if not skill.enabled:
            continue
        resolved_skill = _resolve_skill(config.owner_user_id, skill, skill_repo)
        if resolved_skill.name in seen_skill_names:
            raise ValueError(f"Duplicate Skill name in AgentConfig: {resolved_skill.name}")
        seen_skill_names.add(resolved_skill.name)
        resolved_skills.append(resolved_skill)
    enabled_mcp_servers = []
    seen_mcp_server_names: set[str] = set()
    for server in config.mcp_servers:
        if not server.enabled:
            continue
        if server.name in seen_mcp_server_names:
            raise ValueError(f"Duplicate MCP server name in AgentConfig: {server.name}")
        seen_mcp_server_names.add(server.name)
        enabled_mcp_servers.append(server)
    return ResolvedAgentConfig(
        id=config.id,
        name=config.name,
        description=config.description,
        model=config.model,
        tools=list(config.tools),
        system_prompt=config.system_prompt,
        runtime_settings=dict(config.runtime_settings),
        compact=dict(config.compact),
        skills=resolved_skills,
        rules=[rule for rule in config.rules if rule.enabled],
        sub_agents=[agent for agent in config.sub_agents if agent.enabled],
        mcp_servers=enabled_mcp_servers,
        meta=dict(config.meta),
    )


def _resolve_skill(owner_user_id: str, skill: AgentSkill, skill_repo: Any) -> ResolvedSkill:
    if skill_repo is None:
        raise RuntimeError("skill_repo is required to resolve AgentConfig Skills")

    package = skill_repo.get_package(owner_user_id, skill.package_id)
    if package is None:
        raise RuntimeError(f"Skill package not found while resolving AgentConfig: {skill.package_id}")
    if package.skill_id != skill.skill_id:
        raise RuntimeError(f"Skill package {skill.package_id} does not belong to Skill {skill.skill_id}")
    document = parse_skill_document(package.skill_md, label=f"Skill {skill.skill_id!r} on Agent config")
    name = document.name
    description = document.frontmatter.get("description", "")
    if not isinstance(description, str):
        description = ""
    resolved = ResolvedSkill(
        id=skill.skill_id,
        name=name,
        description=description,
        version=package.version,
        content=package.skill_md,
        files=dict(package.files),
        source=dict(package.source),
    )
    return validate_resolved_skill_content(resolved)


def validate_resolved_skill_content(skill: ResolvedSkill) -> ResolvedSkill:
    document = parse_skill_document(skill.content, label=f"Skill {skill.name!r} on Agent config")
    if document.name != skill.name:
        raise ValueError(f"Skill {skill.name!r} on Agent config frontmatter name must match ResolvedSkill.name")
    return skill
