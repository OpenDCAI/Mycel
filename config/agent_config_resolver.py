from __future__ import annotations

import re

import yaml

from config.agent_config_types import AgentConfig, AgentSkill, ResolvedAgentConfig

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def resolve_agent_config(config: AgentConfig) -> ResolvedAgentConfig:
    enabled_skills = []
    seen_skill_names: set[str] = set()
    for skill in config.skills:
        if not skill.enabled:
            continue
        if skill.name in seen_skill_names:
            raise ValueError(f"Duplicate Skill name in AgentConfig: {skill.name}")
        seen_skill_names.add(skill.name)
        enabled_skills.append(validate_agent_skill_content(skill))
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
        skills=enabled_skills,
        rules=[rule for rule in config.rules if rule.enabled],
        sub_agents=[agent for agent in config.sub_agents if agent.enabled],
        mcp_servers=enabled_mcp_servers,
        meta=dict(config.meta),
    )


def validate_agent_skill_content(skill: AgentSkill) -> AgentSkill:
    if not skill.content.strip():
        raise ValueError(f"Skill {skill.name!r} on Agent config has blank content")
    frontmatter_result = _FRONTMATTER_RE.search(skill.content)
    if frontmatter_result is None:
        raise ValueError(f"Skill {skill.name!r} on Agent config is missing SKILL.md frontmatter")
    frontmatter = yaml.safe_load(frontmatter_result.group(1)) or {}
    if not isinstance(frontmatter, dict):
        raise ValueError(f"Skill {skill.name!r} on Agent config frontmatter must be a mapping")
    frontmatter_name = frontmatter.get("name")
    if not isinstance(frontmatter_name, str) or not frontmatter_name.strip():
        raise ValueError(f"Skill {skill.name!r} on Agent config frontmatter is missing name")
    if frontmatter_name.strip() != skill.name:
        raise ValueError(f"Skill {skill.name!r} on Agent config frontmatter name must match AgentSkill.name")
    return skill
