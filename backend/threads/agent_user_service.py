"""Agent User CRUD over repo-backed users/configs."""

import time
from pathlib import Path
from typing import Any

from backend.hub.versioning import BumpType, bump_semver
from backend.identity.avatar.urls import avatar_url
from config.agent_config_types import AgentConfig, AgentRule, AgentSkill, AgentSubAgent, McpServerConfig
from config.defaults.tool_catalog import TOOLS_BY_NAME, ToolDef, tool_enabled_for_agent
from config.loader import AgentLoader

_SYSTEM_AGENTS_DIR = (Path(__file__).resolve().parents[2] / "config" / "defaults" / "agents").resolve()
_MCP_CONFIG_KEYS = ("transport", "command", "args", "env", "url", "allowed_tools", "instructions")
INITIAL_AGENT_CONFIG_VERSION = "1.0.0"


def _tools_from_repo(config: AgentConfig) -> list[dict[str, Any]]:
    runtime = config.runtime_settings
    enabled_tools = ["*"] if config.tools is None else config.tools
    tools_list = []
    for tool_name, tool_info in TOOLS_BY_NAME.items():
        runtime_key = f"tools:{tool_name}"
        override = runtime.get(runtime_key, {}) if isinstance(runtime.get(runtime_key), dict) else {}
        tools_list.append(
            {
                "name": tool_name,
                "enabled": tool_enabled_for_agent(tool_name, configured_tools=enabled_tools, runtime=runtime),
                "desc": override.get("desc") or tool_info.desc,
                "group": tool_info.group,
            }
        )
    return tools_list


def _skills_from_repo(config: AgentConfig, skill_repo: Any = None) -> list[dict[str, Any]]:
    if config.skills and skill_repo is None:
        raise RuntimeError("skill_repo is required for Agent Skill display projection")
    skills_list = []
    for skill in config.skills:
        library_skill = skill_repo.get_by_id(config.owner_user_id, skill.skill_id)
        if library_skill is None:
            raise RuntimeError(f"Library skill not found for Agent Skill display projection: {skill.skill_id}")
        skills_list.append(
            {
                "id": skill.skill_id,
                "name": library_skill.name,
                "enabled": skill.enabled,
                "desc": library_skill.description,
            }
        )
    return skills_list


def _rules_from_repo(config: AgentConfig) -> list[dict[str, Any]]:
    return [{"name": rule.name, "content": rule.content} for rule in config.rules]


def _sub_agents_from_repo(config: AgentConfig) -> list[dict[str, Any]]:
    sub_agents = {item["name"]: item for item in _load_builtin_agents(TOOLS_BY_NAME)}
    for row in config.sub_agents:
        raw_tools = ["*"] if row.tools is None else row.tools
        is_all = raw_tools == ["*"]
        tools = [
            {
                "name": name,
                "enabled": bool(is_all or name in raw_tools),
                "desc": info.desc,
                "group": info.group,
            }
            for name, info in TOOLS_BY_NAME.items()
        ]
        sub_agents[row.name] = {
            "name": row.name,
            "desc": row.description,
            "tools": tools,
            "system_prompt": row.system_prompt,
            "builtin": False,
        }
    return list(sub_agents.values())


def _mcp_servers_from_repo(config: AgentConfig) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for server in config.mcp_servers:
        exposed = server.model_dump(exclude_none=True)
        if exposed.get("args") == []:
            exposed.pop("args")
        items.append(exposed)
    return items


def _compact_from_repo(config: AgentConfig) -> dict[str, Any]:
    compact = config.compact
    if compact is None:
        return {"trigger_tokens": None}
    if not isinstance(compact, dict):
        raise RuntimeError("agent config compact must be a JSON object")
    return {"trigger_tokens": compact.get("trigger_tokens")}


def _source_from_repo(config: AgentConfig) -> dict[str, Any] | None:
    meta = config.meta
    source = meta.get("source") if isinstance(meta.get("source"), dict) else None
    if not source:
        return None
    return dict(source)


def _agent_user_from_repos(user: Any, agent_config_repo: Any, skill_repo: Any = None) -> dict[str, Any]:
    if user.agent_config_id is None:
        raise RuntimeError(f"Agent user {user.id} is missing agent_config_id")
    config = agent_config_repo.get_agent_config(user.agent_config_id)
    if config is None:
        raise RuntimeError(f"Agent config {user.agent_config_id} is missing for {user.id}")
    item = {
        "id": user.id,
        "name": config.name or user.display_name,
        "description": config.description,
        "model": config.model,
        "status": config.status,
        "version": config.version,
        "avatar_url": avatar_url(user.id, bool(user.avatar)),
        "config": {
            "prompt": config.system_prompt,
            "rules": _rules_from_repo(config),
            "tools": _tools_from_repo(config),
            "mcpServers": _mcp_servers_from_repo(config),
            "skills": _skills_from_repo(config, skill_repo),
            "subAgents": _sub_agents_from_repo(config),
            "compact": _compact_from_repo(config),
        },
        "created_at": 0,
        "updated_at": 0,
    }
    source = _source_from_repo(config)
    if source is not None:
        item["source"] = source
    return item


def _agent_user_summary_from_repos(user: Any, agent_config_repo: Any) -> dict[str, Any]:
    if user.agent_config_id is None:
        raise RuntimeError(f"Agent user {user.id} is missing agent_config_id")
    config = agent_config_repo.get_agent_config(user.agent_config_id)
    if config is None:
        raise RuntimeError(f"Agent config {user.agent_config_id} is missing for {user.id}")
    item = {
        "id": user.id,
        "name": config.name or user.display_name,
        "description": config.description,
        "model": config.model,
        "status": config.status,
        "version": config.version,
        "avatar_url": avatar_url(user.id, bool(user.avatar)),
        "created_at": 0,
        "updated_at": 0,
    }
    source = _source_from_repo(config)
    if source is not None:
        item["source"] = source
    return item


# ── Leon builtin ──


def _leon_builtin() -> dict[str, Any]:
    """Build Leon builtin agent-user dict with full tool catalog."""
    tools = [{"name": k, "enabled": v.default, "desc": v.desc, "group": v.group} for k, v in TOOLS_BY_NAME.items()]
    # Load built-in sub-agents (read-only display)
    builtin_agents = _load_builtin_agents(TOOLS_BY_NAME)

    return {
        "id": "__leon__",
        "name": "Mycel",
        "description": "Universal digital worker, ready to work for you",
        "status": "active",
        "version": "1.0.0",
        "config": {"prompt": "", "rules": [], "tools": tools, "mcpServers": [], "skills": [], "subAgents": builtin_agents},
        "created_at": 0,
        "updated_at": 0,
        "builtin": True,
    }


def _load_builtin_agents(catalog: dict[str, ToolDef]) -> list[dict[str, Any]]:
    """Load system built-in agents for display (read-only)."""
    loader = AgentLoader()
    agents = []
    if _SYSTEM_AGENTS_DIR.is_dir():
        for md in sorted(_SYSTEM_AGENTS_DIR.glob("*.md")):
            ac = loader.parse_agent_file(md)
            if ac:
                is_all = ac.tools == ["*"]
                agent_tools = [
                    {"name": k, "enabled": is_all or k in ac.tools, "desc": v.desc, "group": v.group} for k, v in catalog.items()
                ]
                agents.append(
                    {
                        "name": ac.name,
                        "desc": ac.description,
                        "tools": agent_tools,
                        "system_prompt": ac.system_prompt,
                        "builtin": True,
                    }
                )
    return agents


# ── CRUD operations ──


def list_agent_users(
    owner_user_id: str | None = None,
    user_repo: Any = None,
    agent_config_repo: Any = None,
    skill_repo: Any = None,
) -> list[dict[str, Any]]:
    """List agent users. If owner_user_id given, only that user's agents (no builtin Leon).

    Args:
        owner_user_id: Filter to agents owned by this user.
        user_repo: Injected UserRepo for agent ownership lookup.
    """
    # @@@auth-scope - scoped by owner and config repos.
    if owner_user_id:
        if user_repo is None or agent_config_repo is None:
            raise RuntimeError("user_repo and agent_config_repo are required when owner_user_id is provided")
        agents = user_repo.list_by_owner_user_id(owner_user_id)
        return [_agent_user_from_repos(agent, agent_config_repo, skill_repo) for agent in agents]

    # Unscoped path is builtin-only. Owner-scoped callers must use repos.
    return [_leon_builtin()]


def list_agent_user_summaries(
    owner_user_id: str | None = None,
    user_repo: Any = None,
    agent_config_repo: Any = None,
) -> list[dict[str, Any]]:
    if owner_user_id:
        if user_repo is None or agent_config_repo is None:
            raise RuntimeError("user_repo and agent_config_repo are required when owner_user_id is provided")
        agents = user_repo.list_by_owner_user_id(owner_user_id)
        return [_agent_user_summary_from_repos(agent, agent_config_repo) for agent in agents]
    return [_leon_builtin()]


def get_agent_user(
    agent_user_id: str,
    *,
    user_repo: Any = None,
    agent_config_repo: Any = None,
    skill_repo: Any = None,
) -> dict[str, Any] | None:
    if agent_user_id == "__leon__":
        return _leon_builtin()
    if user_repo is None or agent_config_repo is None:
        raise RuntimeError("user_repo and agent_config_repo are required for agent user reads")
    user = user_repo.get_by_id(agent_user_id)
    if user is None:
        return None
    return _agent_user_from_repos(user, agent_config_repo, skill_repo)


def create_agent_user(
    name: str,
    description: str = "",
    owner_user_id: str | None = None,
    user_repo: Any = None,
    agent_config_repo: Any = None,
    contact_repo: Any = None,
) -> dict[str, Any]:
    from backend.identity.contact_bootstrap import ensure_owner_agent_contact
    from storage.contracts import UserRow, UserType
    from storage.utils import generate_agent_config_id, generate_agent_user_id

    now = time.time()
    agent_user_id = generate_agent_user_id()
    agent_config_id = generate_agent_config_id()

    # Persist to users table so panel/auth shells see a unified agent identity
    if owner_user_id:
        row = UserRow(
            id=agent_user_id,
            type=UserType.AGENT,
            display_name=name,
            owner_user_id=owner_user_id,
            agent_config_id=agent_config_id,
            created_at=now,
        )
        if user_repo is None:
            raise RuntimeError("user_repo is required when owner_user_id is provided")
        user_repo.create(row)

    # @@@agent-user-before-config - new schema roots agent_configs on agent_user_id.
    # The user row must exist before the config write, otherwise the live DB
    # rejects the insert on the forward reference.
    if agent_config_repo:
        if owner_user_id is None:
            raise RuntimeError("owner_user_id is required when creating repo-backed agent configs")
        _save_config_to_repo(
            agent_config_repo,
            agent_config_id,
            agent_user_id=agent_user_id,
            owner_user_id=owner_user_id,
            name=name,
            description=description,
            status="draft",
            version=INITIAL_AGENT_CONFIG_VERSION,
        )

    created = get_agent_user(agent_user_id, user_repo=user_repo, agent_config_repo=agent_config_repo)
    if created is None:
        raise RuntimeError(f"Created agent user {agent_user_id} was not readable")
    if owner_user_id:
        ensure_owner_agent_contact(contact_repo, owner_user_id, agent_user_id, now=now)
    return created


def _require_repo_backed_agent_ops(user_repo: Any = None, agent_config_repo: Any = None) -> None:
    if user_repo is None or agent_config_repo is None:
        raise RuntimeError("user_repo and agent_config_repo are required for owner-scoped agent operations")


def update_agent_user(
    agent_user_id: str,
    user_repo: Any = None,
    agent_config_repo: Any = None,
    skill_repo: Any = None,
    *,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    if agent_user_id == "__leon__":
        raise RuntimeError("Builtin agent is read-only")
    user, config = _resolve_repo_backed_agent(agent_user_id, user_repo, agent_config_repo)
    if user is None or config is None:
        return None
    updates = {key: value for key, value in {"name": name, "description": description, "status": status}.items() if value is not None}
    if not updates:
        return get_agent_user(agent_user_id, user_repo=user_repo, agent_config_repo=agent_config_repo, skill_repo=skill_repo)
    if "name" in updates:
        user_repo.update(agent_user_id, display_name=updates["name"])
    agent_config_repo.save_agent_config(
        config.model_copy(
            update={
                "name": updates.get("name", config.name or user.display_name),
                "description": updates.get("description", config.description),
                "status": updates.get("status", config.status),
            }
        )
    )

    return get_agent_user(agent_user_id, user_repo=user_repo, agent_config_repo=agent_config_repo, skill_repo=skill_repo)


def update_agent_user_config(
    agent_user_id: str,
    config_patch: dict[str, Any],
    user_repo: Any = None,
    agent_config_repo: Any = None,
    skill_repo: Any = None,
) -> dict[str, Any] | None:
    if agent_user_id == "__leon__":
        raise RuntimeError("Builtin agent is read-only")
    return _sync_agent_config_patch_to_repo(agent_user_id, config_patch, user_repo, agent_config_repo, skill_repo)


def select_agent_skill(
    agent_user_id: str,
    skill_id: str,
    user_repo: Any = None,
    agent_config_repo: Any = None,
    skill_repo: Any = None,
) -> dict[str, Any] | None:
    if skill_repo is None:
        raise RuntimeError("skill_repo is required for agent config skill writes")
    user, current_config = _resolve_repo_backed_agent(agent_user_id, user_repo, agent_config_repo)
    if user is None or current_config is None:
        return None
    if user.owner_user_id != current_config.owner_user_id:
        raise RuntimeError(f"Agent user owner does not match Agent config owner: {agent_user_id}")
    library_skill = skill_repo.get_by_id(current_config.owner_user_id, skill_id)
    if library_skill is None:
        raise RuntimeError(f"Library skill not found: {skill_id}")
    current_items = [
        {"id": skill.skill_id, "enabled": skill.enabled} for skill in current_config.skills if skill.skill_id != library_skill.id
    ]
    current_items.append({"id": library_skill.id, "enabled": True})
    return _sync_agent_config_patch_to_repo(
        agent_user_id,
        {"skills": current_items},
        user_repo,
        agent_config_repo,
        skill_repo,
    )


# ── Agent config repo helpers ──


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
    version: str,
    runtime_settings: dict | None = None,
    mcp_servers: list[McpServerConfig] | None = None,
    meta: dict | None = None,
) -> None:
    agent_config_repo.save_agent_config(
        AgentConfig(
            id=agent_config_id,
            agent_user_id=agent_user_id,
            owner_user_id=owner_user_id,
            name=name,
            description=description,
            model=model,
            tools=["*"] if tools is None else tools,
            system_prompt=system_prompt,
            status=status,
            version=version,
            runtime_settings=runtime_settings or {},
            mcp_servers=mcp_servers or [],
            meta=meta or {},
        )
    )


def _runtime_and_tools_from_patch(current_config: AgentConfig, config_patch: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    runtime = dict(current_config.runtime_settings)
    tools = list(["*"] if current_config.tools is None else current_config.tools)

    if "tools" in config_patch and config_patch["tools"] is not None:
        tool_items = [item for item in config_patch["tools"] if isinstance(item, dict) and item.get("name")]
        runtime = {k: v for k, v in runtime.items() if not k.startswith("tools:")}
        enabled_tools = []
        for item in tool_items:
            enabled = _enabled_from_patch_item(item, label="Tool patch item")
            runtime[f"tools:{item['name']}"] = {
                "enabled": enabled,
                "desc": item.get("desc", ""),
            }
            if enabled:
                enabled_tools.append(item["name"])
        tools = ["*"] if tool_items and len(enabled_tools) == len(tool_items) else enabled_tools

    return runtime, tools


def _compact_from_patch(current_config: AgentConfig, config_patch: dict[str, Any]) -> dict[str, Any]:
    current = current_config.compact
    if current is None:
        compact: dict[str, Any] = {}
    elif isinstance(current, dict):
        compact = dict(current)
    else:
        raise RuntimeError("agent config compact must be a JSON object")

    if "compact" not in config_patch or config_patch["compact"] is None:
        return compact

    patch = config_patch["compact"]
    if not isinstance(patch, dict):
        raise RuntimeError("agent config patch compact must be a JSON object")

    if "trigger_tokens" in patch:
        trigger_tokens = patch["trigger_tokens"]
        if trigger_tokens is not None and not isinstance(trigger_tokens, int):
            raise RuntimeError("agent config patch compact.trigger_tokens must be an integer or null")
        compact["trigger_tokens"] = trigger_tokens

    return compact


def _mcp_from_patch(config_patch: dict[str, Any], current_config: AgentConfig) -> list[McpServerConfig]:
    if "mcpServers" not in config_patch or config_patch["mcpServers"] is None:
        return list(current_config.mcp_servers)
    servers: list[McpServerConfig] = []
    seen_names: set[str] = set()
    for item in config_patch["mcpServers"]:
        if not (isinstance(item, dict) and item.get("name")):
            raise RuntimeError("MCP server patch item must include name")
        if "disabled" in item:
            raise RuntimeError("MCP server patch item must use enabled, not disabled")
        enabled = _enabled_from_patch_item(item, label="MCP server patch item")
        name = str(item["name"])
        if name in seen_names:
            raise RuntimeError(f"Duplicate MCP server name in patch: {name}")
        seen_names.add(name)
        direct_config = {key: item[key] for key in _MCP_CONFIG_KEYS if key in item and item[key] is not None}
        if "command" not in direct_config and "url" not in direct_config:
            raise RuntimeError(f"MCP server config must include command or url: {name}")
        servers.append(
            McpServerConfig(
                name=name,
                transport=direct_config.get("transport"),
                command=direct_config.get("command"),
                args=_json_array_from_patch_item(direct_config.get("args"), label="MCP server patch item args"),
                env=_json_object_from_patch_item(direct_config.get("env"), label="MCP server patch item env"),
                url=direct_config.get("url"),
                instructions=direct_config.get("instructions"),
                allowed_tools=direct_config.get("allowed_tools"),
                enabled=enabled,
            )
        )
    return servers


def _enabled_from_patch_item(item: dict[str, Any], *, label: str) -> bool:
    if "enabled" not in item:
        return True
    enabled = item["enabled"]
    if not isinstance(enabled, bool):
        raise RuntimeError(f"{label} enabled must be a boolean")
    return enabled


def _json_array_from_patch_item(value: Any, *, label: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be a JSON array")
    return list(value)


def _json_object_from_patch_item(value: Any, *, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object")
    return dict(value)


def _rules_from_patch(current_config: AgentConfig, config_patch: dict[str, Any]) -> list[AgentRule]:
    if "rules" not in config_patch or config_patch["rules"] is None:
        return list(current_config.rules)
    rules: list[AgentRule] = []
    seen_names: set[str] = set()
    if "rules" in config_patch and config_patch["rules"] is not None:
        for rule in config_patch["rules"]:
            if not (isinstance(rule, dict) and rule.get("name")):
                raise RuntimeError("Rule patch item must include name")
            name = str(rule["name"])
            if name in seen_names:
                raise RuntimeError(f"Duplicate Rule name in patch: {name}")
            seen_names.add(name)
            rules.append(AgentRule(name=name, content=str(rule.get("content", ""))))
    return rules


def _sub_agents_from_patch(current_config: AgentConfig, config_patch: dict[str, Any]) -> list[AgentSubAgent]:
    if "subAgents" not in config_patch or config_patch["subAgents"] is None:
        return list(current_config.sub_agents)
    sub_agents: list[AgentSubAgent] = []
    seen_names: set[str] = set()
    if "subAgents" in config_patch and config_patch["subAgents"] is not None:
        for item in config_patch["subAgents"]:
            if not (isinstance(item, dict) and item.get("name")):
                raise RuntimeError("SubAgent patch item must include name")
            if item.get("builtin"):
                continue
            name = str(item["name"])
            if name in seen_names:
                raise RuntimeError(f"Duplicate SubAgent name in patch: {name}")
            seen_names.add(name)
            raw_tools = _json_array_from_patch_item(item.get("tools"), label="SubAgent patch item tools")
            if isinstance(raw_tools, list) and raw_tools and isinstance(raw_tools[0], dict):
                enabled_tools = []
                for tool in raw_tools:
                    if not isinstance(tool, dict):
                        continue
                    enabled = _enabled_from_patch_item(tool, label="SubAgent tool patch item")
                    if enabled:
                        enabled_tools.append(tool["name"])
            else:
                enabled_tools = list(raw_tools)
            sub_agents.append(
                AgentSubAgent(
                    name=name,
                    description=str(item.get("desc", "")),
                    tools=enabled_tools,
                    system_prompt=str(item.get("system_prompt", "")),
                )
            )
    return sub_agents


def _selected_library_package(owner_user_id: str, library_skill: Any, skill_repo: Any) -> Any:
    package_id = getattr(library_skill, "package_id", None)
    if not package_id:
        raise RuntimeError(f"Library skill has no selected package: {library_skill.id}")
    package = skill_repo.get_package(owner_user_id, package_id)
    if package is None:
        raise RuntimeError(f"Library skill selected package not found: {package_id}")
    if getattr(package, "skill_id", None) != library_skill.id:
        raise RuntimeError(f"Library skill selected package does not belong to Skill: {package_id}")
    return package


def _current_skill_by_id(config: AgentConfig, skill_id: str) -> AgentSkill | None:
    for skill in config.skills:
        if skill.skill_id == skill_id:
            return skill
    return None


def _patch_library_skill_id(item: dict[str, Any]) -> str:
    value = item.get("id")
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("Skill patch item must include id")
    return value


def _skills_from_patch(current_config: AgentConfig, config_patch: dict[str, Any], owner_user_id: str, skill_repo: Any) -> list[AgentSkill]:
    if "skills" not in config_patch or config_patch["skills"] is None:
        return list(current_config.skills)
    if skill_repo is None:
        raise RuntimeError("skill_repo is required for agent config skill writes")

    skills: list[AgentSkill] = []
    seen_names: set[str] = set()
    seen_skill_ids: set[str] = set()
    skill_items = config_patch["skills"]
    for item in skill_items:
        if not isinstance(item, dict):
            raise RuntimeError("Skill patch item must be an object")
        if "name" in item or "desc" in item:
            raise RuntimeError("Skill patch item must not include name or desc")
        if "content" in item or "files" in item:
            raise RuntimeError("Skill patch item must not include content or files")
        if "source" in item or "version" in item:
            raise RuntimeError("Skill patch item must not include source or version")
        if "skill_id" in item:
            raise RuntimeError("Skill patch item must use id")
        if "disabled" in item:
            raise RuntimeError("Skill patch item must use enabled, not disabled")
        _enabled_from_patch_item(item, label="Skill patch item")
        library_skill_id = _patch_library_skill_id(item)
        if library_skill_id in seen_skill_ids:
            raise RuntimeError(f"Duplicate Skill id in patch: {library_skill_id}")
        seen_skill_ids.add(library_skill_id)
    for item in skill_items:
        enabled = _enabled_from_patch_item(item, label="Skill patch item")
        library_skill_id = _patch_library_skill_id(item)
        current_skill = _current_skill_by_id(current_config, library_skill_id)
        library_skill = skill_repo.get_by_id(owner_user_id, library_skill_id)
        if library_skill is None:
            raise RuntimeError(f"Library skill not found: {library_skill_id}")
        if library_skill.name in seen_names:
            raise RuntimeError(f"Duplicate Skill name in patch: {library_skill.name}")
        seen_names.add(library_skill.name)
        library_package = _selected_library_package(owner_user_id, library_skill, skill_repo)
        skills.append(
            AgentSkill(
                id=current_skill.id if current_skill is not None else None,
                skill_id=library_skill.id,
                package_id=library_package.id,
                enabled=enabled,
            )
        )
    return skills


def _sync_agent_config_patch_to_repo(
    agent_user_id: str, config_patch: dict[str, Any], user_repo: Any, agent_config_repo: Any, skill_repo: Any = None
) -> dict[str, Any] | None:
    user, current_config = _resolve_repo_backed_agent(agent_user_id, user_repo, agent_config_repo)
    if user is None or current_config is None:
        return None

    runtime, tools = _runtime_and_tools_from_patch(current_config, config_patch)
    updated_config = current_config.model_copy(
        update={
            "name": current_config.name or user.display_name,
            "description": current_config.description,
            "model": current_config.model,
            "tools": tools,
            "system_prompt": config_patch.get("prompt", current_config.system_prompt),
            "status": current_config.status,
            "version": current_config.version,
            "runtime_settings": runtime,
            "compact": _compact_from_patch(current_config, config_patch),
            "mcp_servers": _mcp_from_patch(config_patch, current_config),
            "skills": _skills_from_patch(current_config, config_patch, current_config.owner_user_id, skill_repo),
            "rules": _rules_from_patch(current_config, config_patch),
            "sub_agents": _sub_agents_from_patch(current_config, config_patch),
        }
    )
    agent_config_repo.save_agent_config(updated_config)
    return get_agent_user(agent_user_id, user_repo=user_repo, agent_config_repo=agent_config_repo, skill_repo=skill_repo)


# ── Publish / Delete ──


def publish_agent_user(
    agent_user_id: str,
    bump_type: BumpType = "patch",
    user_repo: Any = None,
    agent_config_repo: Any = None,
    skill_repo: Any = None,
) -> dict[str, Any] | None:
    user, config = _resolve_repo_backed_agent(agent_user_id, user_repo, agent_config_repo)
    if user is None or config is None:
        return None
    next_version = bump_semver(config.version, bump_type)

    agent_config_repo.save_agent_config(config.model_copy(update={"version": next_version, "status": "active"}))

    return get_agent_user(agent_user_id, user_repo=user_repo, agent_config_repo=agent_config_repo, skill_repo=skill_repo)


def _resolve_repo_backed_agent(
    agent_user_id: str, user_repo: Any = None, agent_config_repo: Any = None
) -> tuple[Any | None, AgentConfig | None]:
    _require_repo_backed_agent_ops(user_repo, agent_config_repo)
    user = user_repo.get_by_id(agent_user_id)
    if user is None or user.agent_config_id is None:
        return None, None
    config = agent_config_repo.get_agent_config(user.agent_config_id)
    if config is None:
        raise RuntimeError(f"Agent config {user.agent_config_id} is missing for {agent_user_id}")
    return user, config


def delete_agent_user(
    agent_user_id: str,
    user_repo: Any = None,
    agent_config_repo: Any = None,
    contact_repo: Any = None,
) -> bool:
    if agent_user_id == "__leon__":
        return False
    _require_repo_backed_agent_ops(user_repo, agent_config_repo)
    if contact_repo is None:
        raise RuntimeError("contact_repo is required for agent delete")
    user = user_repo.get_by_id(agent_user_id)
    if user is None:
        return False

    if user.agent_config_id is None:
        raise RuntimeError(f"Agent user {agent_user_id} is missing agent_config_id")
    # @@@delete-agent-order - fail before deleting roots if dependency cleanup fails.
    contact_repo.delete_for_user(agent_user_id)
    agent_config_repo.delete_agent_config(user.agent_config_id)

    # Also remove from unified users table
    user_repo.delete(agent_user_id)

    return True
