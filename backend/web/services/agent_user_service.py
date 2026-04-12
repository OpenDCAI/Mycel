"""Agent-user CRUD over repo-backed users/configs."""

import re
import time
from pathlib import Path
from typing import Any

import yaml

from backend.web.utils.serializers import avatar_url
from backend.web.utils.versioning import BumpType, bump_semver
from config.defaults.tool_catalog import TOOLS_BY_NAME, ToolDef
from config.loader import AgentLoader

_SYSTEM_AGENTS_DIR = (Path(__file__).resolve().parents[3] / "config" / "defaults" / "agents").resolve()


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


def _tools_from_repo(config: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    enabled_tools = config.get("tools") or ["*"]
    is_all = enabled_tools == ["*"]
    tools_list = []
    for tool_name, tool_info in TOOLS_BY_NAME.items():
        runtime_key = f"tools:{tool_name}"
        override = runtime.get(runtime_key, {}) if isinstance(runtime.get(runtime_key), dict) else {}
        tools_list.append(
            {
                "name": tool_name,
                "enabled": bool(override.get("enabled", is_all or tool_name in enabled_tools)),
                "desc": override.get("desc") or tool_info.desc,
                "group": tool_info.group,
            }
        )
    return tools_list


def _skills_from_repo(agent_config_id: str, config: dict[str, Any], agent_config_repo: Any) -> list[dict[str, Any]]:
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    skills_list = []
    for row in agent_config_repo.list_skills(agent_config_id):
        runtime_key = f"skills:{row['name']}"
        override = runtime.get(runtime_key, {}) if isinstance(runtime.get(runtime_key), dict) else {}
        desc = override.get("desc")
        if not desc:
            from backend.web.services.library_service import get_library_skill_desc

            desc = get_library_skill_desc(str(row["name"]))
        skills_list.append(
            {
                "name": row["name"],
                "enabled": bool(override.get("enabled", True)),
                "desc": desc or "",
            }
        )
    return skills_list


def _rules_from_repo(agent_config_id: str, agent_config_repo: Any) -> list[dict[str, Any]]:
    rules = []
    for row in agent_config_repo.list_rules(agent_config_id):
        filename = str(row.get("filename") or "")
        rules.append({"name": filename.removesuffix(".md"), "content": row.get("content", "")})
    return rules


def _sub_agents_from_repo(agent_config_id: str, agent_config_repo: Any) -> list[dict[str, Any]]:
    sub_agents = {item["name"]: item for item in _load_builtin_agents(TOOLS_BY_NAME)}
    for row in agent_config_repo.list_sub_agents(agent_config_id):
        raw_tools = row.get("tools_json") or row.get("tools") or ["*"]
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
        sub_agents[row["name"]] = {
            "name": row["name"],
            "desc": row.get("description", ""),
            "tools": tools,
            "system_prompt": row.get("system_prompt", ""),
            "builtin": False,
        }
    return list(sub_agents.values())


def _mcps_from_repo(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw = config.get("mcp", {}) if isinstance(config.get("mcp"), dict) else {}
    return [
        {
            "name": name,
            "command": item.get("command", ""),
            "args": item.get("args", []),
            "env": item.get("env", {}),
            "disabled": item.get("disabled", False),
        }
        for name, item in raw.items()
        if isinstance(item, dict)
    ]


def _compact_from_repo(config: dict[str, Any]) -> dict[str, Any]:
    compact = config.get("compact")
    if compact is None:
        return {"trigger_tokens": None}
    if not isinstance(compact, dict):
        raise RuntimeError("agent config compact must be a JSON object")
    return {"trigger_tokens": compact.get("trigger_tokens")}


def _agent_user_from_repos(user: Any, agent_config_repo: Any) -> dict[str, Any]:
    if user.agent_config_id is None:
        raise RuntimeError(f"Agent user {user.id} is missing agent_config_id")
    config = agent_config_repo.get_config(user.agent_config_id)
    if config is None:
        raise RuntimeError(f"Agent config {user.agent_config_id} is missing for {user.id}")
    return {
        "id": user.id,
        "name": config.get("name") or user.display_name,
        "description": config.get("description", ""),
        "model": config.get("model"),
        "status": config.get("status", "draft"),
        "version": config.get("version", "0.1.0"),
        "avatar_url": avatar_url(user.id, bool(user.avatar)),
        "config": {
            "prompt": config.get("system_prompt", ""),
            "rules": _rules_from_repo(user.agent_config_id, agent_config_repo),
            "tools": _tools_from_repo(config),
            "mcps": _mcps_from_repo(config),
            "skills": _skills_from_repo(user.agent_config_id, config, agent_config_repo),
            "subAgents": _sub_agents_from_repo(user.agent_config_id, agent_config_repo),
            "compact": _compact_from_repo(config),
        },
        "created_at": config.get("created_at", 0),
        "updated_at": config.get("updated_at", 0),
    }


def _agent_user_summary_from_repos(user: Any, agent_config_repo: Any) -> dict[str, Any]:
    if user.agent_config_id is None:
        raise RuntimeError(f"Agent user {user.id} is missing agent_config_id")
    config = agent_config_repo.get_config(user.agent_config_id)
    if config is None:
        raise RuntimeError(f"Agent config {user.agent_config_id} is missing for {user.id}")
    return {
        "id": user.id,
        "name": config.get("name") or user.display_name,
        "description": config.get("description", ""),
        "model": config.get("model"),
        "status": config.get("status", "draft"),
        "version": config.get("version", "0.1.0"),
        "avatar_url": avatar_url(user.id, bool(user.avatar)),
        "created_at": config.get("created_at", 0),
        "updated_at": config.get("updated_at", 0),
    }


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
        "config": {"prompt": "", "rules": [], "tools": tools, "mcps": [], "skills": [], "subAgents": builtin_agents},
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


def list_agent_users(owner_user_id: str | None = None, user_repo: Any = None, agent_config_repo: Any = None) -> list[dict[str, Any]]:
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
        return [_agent_user_from_repos(agent, agent_config_repo) for agent in agents]

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


def get_agent_user(agent_user_id: str, *, user_repo: Any = None, agent_config_repo: Any = None) -> dict[str, Any] | None:
    if agent_user_id == "__leon__":
        return _leon_builtin()
    if user_repo is None or agent_config_repo is None:
        raise RuntimeError("user_repo and agent_config_repo are required for agent user reads")
    user = user_repo.get_by_id(agent_user_id)
    if user is None:
        return None
    return _agent_user_from_repos(user, agent_config_repo)


def create_agent_user(
    name: str,
    description: str = "",
    owner_user_id: str | None = None,
    user_repo: Any = None,
    agent_config_repo: Any = None,
    contact_repo: Any = None,
) -> dict[str, Any]:
    from backend.web.services.contact_bootstrap_service import ensure_owner_agent_contact
    from storage.contracts import UserRow, UserType
    from storage.utils import generate_agent_config_id, generate_agent_user_id

    now = time.time()
    now_ms = int(now * 1000)
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
    # The user row must exist before the config write, otherwise live staging
    # rejects the insert on the forward reference.
    if agent_config_repo:
        _save_config_to_repo(
            agent_config_repo,
            agent_config_id,
            agent_user_id=agent_user_id,
            name=name,
            description=description,
            status="draft",
            version="0.1.0",
            created_at=now_ms,
            updated_at=now_ms,
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
    updates = {
        key: value
        for key, value in {"name": name, "description": description, "status": status}.items()
        if value is not None
    }
    if not updates:
        return get_agent_user(agent_user_id, user_repo=user_repo, agent_config_repo=agent_config_repo)
    if "name" in updates:
        user_repo.update(agent_user_id, display_name=updates["name"])
    agent_config_repo.save_config(
        user.agent_config_id,
        {
            **config,
            "name": updates.get("name", config.get("name") or user.display_name),
            "description": updates.get("description", config.get("description", "")),
            "status": updates.get("status", config.get("status", "draft")),
            "updated_at": int(time.time() * 1000),
        },
    )

    return get_agent_user(agent_user_id, user_repo=user_repo, agent_config_repo=agent_config_repo)


def update_agent_user_config(
    agent_user_id: str,
    config_patch: dict[str, Any],
    user_repo: Any = None,
    agent_config_repo: Any = None,
) -> dict[str, Any] | None:
    if agent_user_id == "__leon__":
        raise RuntimeError("Builtin agent is read-only")
    return _sync_agent_config_patch_to_repo(agent_user_id, config_patch, user_repo, agent_config_repo)


# ── Agent config repo helpers ──


def _save_config_to_repo(
    agent_config_repo: Any,
    agent_config_id: str,
    *,
    agent_user_id: str,
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


def _runtime_and_tools_from_patch(current_config: dict[str, Any], config_patch: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    runtime = dict(current_config.get("runtime", {}) if isinstance(current_config.get("runtime"), dict) else {})
    tools = list(current_config.get("tools") or ["*"])

    if "tools" in config_patch and config_patch["tools"] is not None:
        tool_items = [item for item in config_patch["tools"] if isinstance(item, dict) and item.get("name")]
        runtime = {k: v for k, v in runtime.items() if not k.startswith("tools:")}
        for item in tool_items:
            runtime[f"tools:{item['name']}"] = {
                "enabled": item.get("enabled", True),
                "desc": item.get("desc", ""),
            }
        enabled_tools = [item["name"] for item in tool_items if item.get("enabled", True)]
        tools = ["*"] if tool_items and len(enabled_tools) == len(tool_items) else enabled_tools

    if "skills" in config_patch and config_patch["skills"] is not None:
        skill_items = [item for item in config_patch["skills"] if isinstance(item, dict) and item.get("name")]
        runtime = {k: v for k, v in runtime.items() if not k.startswith("skills:")}
        for item in skill_items:
            runtime[f"skills:{item['name']}"] = {
                "enabled": item.get("enabled", True),
                "desc": item.get("desc", ""),
            }

    return runtime, tools


def _compact_from_patch(current_config: dict[str, Any], config_patch: dict[str, Any]) -> dict[str, Any]:
    current = current_config.get("compact")
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


def _mcp_from_patch(config_patch: dict[str, Any], current_config: dict[str, Any]) -> dict[str, Any]:
    if "mcps" not in config_patch or config_patch["mcps"] is None:
        return dict(current_config.get("mcp", {}) if isinstance(current_config.get("mcp"), dict) else {})
    servers: dict[str, Any] = {}
    for item in config_patch["mcps"]:
        if isinstance(item, dict) and item.get("name"):
            servers[item["name"]] = {
                "command": item.get("command", ""),
                "args": item.get("args", []),
                "env": item.get("env", {}),
                "disabled": item.get("disabled", False),
            }
    return servers


def _sync_repo_children(agent_config_id: str, config_patch: dict[str, Any], agent_config_repo: Any) -> None:
    if "rules" in config_patch and config_patch["rules"] is not None:
        for row in agent_config_repo.list_rules(agent_config_id):
            agent_config_repo.delete_rule(row["id"])
        for rule in config_patch["rules"]:
            if isinstance(rule, dict) and rule.get("name"):
                agent_config_repo.save_rule(agent_config_id, f"{rule['name']}.md", rule.get("content", ""))

    if "skills" in config_patch and config_patch["skills"] is not None:
        existing = {row["name"]: row for row in agent_config_repo.list_skills(agent_config_id)}
        for row in existing.values():
            agent_config_repo.delete_skill(row["id"])
        for skill in config_patch["skills"]:
            if isinstance(skill, dict) and skill.get("name"):
                prior = existing.get(skill["name"], {})
                agent_config_repo.save_skill(
                    agent_config_id,
                    skill["name"],
                    str(prior.get("content", "")),
                    meta=prior.get("meta_json") if isinstance(prior.get("meta_json"), dict) else None,
                )

    if "subAgents" in config_patch and config_patch["subAgents"] is not None:
        for row in agent_config_repo.list_sub_agents(agent_config_id):
            agent_config_repo.delete_sub_agent(row["id"])
        for item in config_patch["subAgents"]:
            if not (isinstance(item, dict) and item.get("name")):
                continue
            if item.get("builtin"):
                continue
            raw_tools = item.get("tools") or []
            if isinstance(raw_tools, list) and raw_tools and isinstance(raw_tools[0], dict):
                enabled_tools = [tool["name"] for tool in raw_tools if tool.get("enabled")]
            else:
                enabled_tools = list(raw_tools)
            agent_config_repo.save_sub_agent(
                agent_config_id,
                item["name"],
                description=item.get("desc", ""),
                tools=enabled_tools,
                system_prompt=item.get("system_prompt", ""),
            )


def _sync_agent_config_patch_to_repo(
    agent_user_id: str, config_patch: dict[str, Any], user_repo: Any, agent_config_repo: Any
) -> dict[str, Any] | None:
    # @@@repo-only-agent-shell - fresh register now creates DB-only agents. Owner-scoped
    # panel edits must use the repo config even when no stale local agent dir exists.
    user, current_config = _resolve_repo_backed_agent(agent_user_id, user_repo, agent_config_repo)
    if user is None or current_config is None:
        return None

    runtime, tools = _runtime_and_tools_from_patch(current_config, config_patch)
    updated_config = {
        **current_config,
        "name": current_config.get("name") or user.display_name,
        "description": current_config.get("description", ""),
        "model": current_config.get("model"),
        "tools": tools,
        "system_prompt": config_patch.get("prompt", current_config.get("system_prompt", "")),
        "status": current_config.get("status", "draft"),
        "version": current_config.get("version", "0.1.0"),
        "created_at": current_config.get("created_at", 0),
        "updated_at": int(time.time() * 1000),
        "runtime": runtime,
        "compact": _compact_from_patch(current_config, config_patch),
        "mcp": _mcp_from_patch(config_patch, current_config),
    }
    agent_config_repo.save_config(user.agent_config_id, updated_config)
    _sync_repo_children(user.agent_config_id, config_patch, agent_config_repo)
    return get_agent_user(agent_user_id, user_repo=user_repo, agent_config_repo=agent_config_repo)


# ── Publish / Delete ──


def publish_agent_user(
    agent_user_id: str,
    bump_type: BumpType = "patch",
    user_repo: Any = None,
    agent_config_repo: Any = None,
) -> dict[str, Any] | None:
    user, config = _resolve_repo_backed_agent(agent_user_id, user_repo, agent_config_repo)
    if user is None or config is None:
        return None
    next_version = bump_semver(config.get("version", "0.1.0"), bump_type)
    updated_at = int(time.time() * 1000)

    agent_config_repo.save_config(
        user.agent_config_id,
        {
            **config,
            "version": next_version,
            "status": "active",
            "updated_at": updated_at,
        },
    )

    return get_agent_user(agent_user_id, user_repo=user_repo, agent_config_repo=agent_config_repo)


def _resolve_repo_backed_agent(
    agent_user_id: str, user_repo: Any = None, agent_config_repo: Any = None
) -> tuple[Any | None, dict[str, Any] | None]:
    _require_repo_backed_agent_ops(user_repo, agent_config_repo)
    user = user_repo.get_by_id(agent_user_id)
    if user is None or user.agent_config_id is None:
        return None, None
    # @@@repo-backed-agent-wins - repo-backed agent users must not silently write
    # to stale local agent dirs just because an old shell still exists.
    config = agent_config_repo.get_config(user.agent_config_id)
    if config is None:
        raise RuntimeError(f"Agent config {user.agent_config_id} is missing for {agent_user_id}")
    return user, config


def delete_agent_user(
    agent_user_id: str,
    user_repo: Any = None,
    agent_config_repo: Any = None,
    thread_launch_pref_repo: Any = None,
    contact_repo: Any = None,
) -> bool:
    if agent_user_id == "__leon__":
        return False
    _require_repo_backed_agent_ops(user_repo, agent_config_repo)
    if thread_launch_pref_repo is None:
        raise RuntimeError("thread_launch_pref_repo is required for agent delete")
    if contact_repo is None:
        raise RuntimeError("contact_repo is required for agent delete")
    user = user_repo.get_by_id(agent_user_id)
    if user is None:
        return False

    if user.agent_config_id is None:
        raise RuntimeError(f"Agent user {agent_user_id} is missing agent_config_id")
    # @@@delete-agent-order - clear dependent rows before the config/user roots.
    # If dependency cleanup fails, refusing the delete is safer than leaving an
    # agent user pointing at a removed config.
    thread_launch_pref_repo.delete_by_agent_user_id(agent_user_id)
    contact_repo.delete_for_user(agent_user_id)
    agent_config_repo.delete_config(user.agent_config_id)

    # Also remove from unified users table
    user_repo.delete(agent_user_id)

    return True


def _sanitize_name(name: str) -> str:
    """Strip path-unsafe characters from snapshot-derived names."""
    sanitized = re.sub(r'[/\\<>:"|?*\x00-\x1f]', "_", name)
    sanitized = sanitized.strip(". ")
    if not sanitized:
        sanitized = "unnamed"
    return sanitized


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
        current_config = agent_config_repo.get_config(agent_config_id) or {}
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

    # @@@snapshot-install-repo-only - marketplace agent installs no longer materialize
    # a local agent directory. The DB is now the live shell; marketplace lineage still needs
    # a separate repo-rooted home because publish records source lineage.
    _save_config_to_repo(
        agent_config_repo,
        agent_config_id,
        agent_user_id=user_id,
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
        skill_meta = skill.get("meta") if isinstance(skill.get("meta"), dict) else None
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
