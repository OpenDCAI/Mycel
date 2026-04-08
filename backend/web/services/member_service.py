"""Member CRUD — file-system based (~/.leon/members/).

Storage layout per member:
    {member_dir}/
    ├── agent.md        # identity (YAML frontmatter + system prompt)
    ├── meta.json       # status, version, timestamps
    ├── runtime.json    # tools/skills enabled + desc
    ├── rules/          # one .md per rule
    ├── agents/         # one .md per sub-agent
    ├── skills/         # one dir per skill
    └── .mcp.json       # MCP server config
"""

import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any

import yaml

from backend.web.core.paths import avatars_dir, members_dir
from backend.web.utils.serializers import avatar_url
from config.defaults.tool_catalog import TOOLS_BY_NAME, ToolDef
from config.loader import AgentLoader

logger = logging.getLogger(__name__)

MEMBERS_DIR = members_dir()
_SYSTEM_AGENTS_DIR = (Path(__file__).resolve().parents[3] / "config" / "defaults" / "agents").resolve()


def _load_tools_catalog() -> dict[str, ToolDef]:
    """Return the typed tool catalog (name → ToolDef)."""
    return TOOLS_BY_NAME


# ── Low-level I/O helpers ──


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


def _write_agent_md(
    path: Path,
    name: str,
    description: str = "",
    model: str | None = None,
    tools: list[str] | None = None,
    system_prompt: str = "",
) -> None:
    fm: dict[str, Any] = {"name": name}
    if description:
        fm["description"] = description
    if model:
        fm["model"] = model
    if tools and tools != ["*"]:
        fm["tools"] = tools
    content = f"---\n{yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()}\n---\n\n{system_prompt}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _parse_agent_md(path: Path) -> dict[str, Any] | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return _parse_agent_md_content(content)


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


# ── Migration: config.json → file structure ──


def _maybe_migrate_config_json(member_dir: Path) -> None:
    """Migrate legacy config.json to file structure, then delete it."""
    cfg_path = member_dir / "config.json"
    if not cfg_path.exists():
        return

    cfg = _read_json(cfg_path, {})
    logger.info("Migrating config.json for member %s", member_dir.name)

    # rules → rules/*.md
    if cfg.get("rules") and isinstance(cfg["rules"], str) and cfg["rules"].strip():
        rules_dir = member_dir / "rules"
        rules_dir.mkdir(exist_ok=True)
        (rules_dir / "default.md").write_text(cfg["rules"], encoding="utf-8")

    # subAgents → agents/*.md
    if cfg.get("subAgents") and isinstance(cfg["subAgents"], list):
        agents_dir = member_dir / "agents"
        agents_dir.mkdir(exist_ok=True)
        for item in cfg["subAgents"]:
            if isinstance(item, dict) and item.get("name"):
                _write_agent_md(
                    agents_dir / f"{item['name']}.md",
                    name=item["name"],
                    description=item.get("desc", ""),
                )

    # tools/skills → runtime.json
    runtime: dict[str, dict[str, Any]] = {}
    for key in ("tools", "skills"):
        items = cfg.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("name"):
                    runtime[f"{key}:{item['name']}"] = {
                        "enabled": item.get("enabled", True),
                        "desc": item.get("desc", ""),
                    }
    if runtime:
        _write_json(member_dir / "runtime.json", runtime)

    # mcps → .mcp.json
    if cfg.get("mcps") and isinstance(cfg["mcps"], list):
        servers: dict[str, Any] = {}
        for item in cfg["mcps"]:
            if isinstance(item, dict) and item.get("name"):
                servers[item["name"]] = {
                    "command": item.get("command", ""),
                    "args": item.get("args", []),
                    "env": item.get("env", {}),
                    "disabled": not item.get("enabled", True),
                }
        if servers:
            _write_json(member_dir / ".mcp.json", {"mcpServers": servers})

    # Remove legacy file
    cfg_path.unlink()
    logger.info("Migrated and removed config.json for member %s", member_dir.name)


# ── Bundle → frontend dict conversion ──


def _member_to_dict(member_dir: Path) -> dict[str, Any] | None:
    """Load member via AgentLoader.load_bundle, convert to frontend format."""
    _maybe_migrate_config_json(member_dir)

    loader = AgentLoader()
    try:
        bundle = loader.load_bundle(member_dir)
    except (ValueError, OSError):
        return None

    agent = bundle.agent
    meta = bundle.meta

    # Build full tools list from catalog + runtime overrides
    catalog = _load_tools_catalog()
    tools_list = []
    for tool_name, tool_info in catalog.items():
        runtime_key = f"tools:{tool_name}"
        if runtime_key in bundle.runtime:
            rc = bundle.runtime[runtime_key]
            tools_list.append({"name": tool_name, "enabled": rc.enabled, "desc": rc.desc or tool_info.desc, "group": tool_info.group})
        else:
            tools_list.append({"name": tool_name, "enabled": tool_info.default, "desc": tool_info.desc, "group": tool_info.group})

    # Skills from runtime — enrich desc from Library if empty
    skills_list = []
    for key, rc in bundle.runtime.items():
        if key.startswith("skills:"):
            skill_name = key.split(":", 1)[-1]
            desc = rc.desc
            if not desc:
                from backend.web.services.library_service import get_library_skill_desc

                desc = get_library_skill_desc(skill_name)
            skills_list.append({"name": skill_name, "enabled": rc.enabled, "desc": desc})

    # Convert rules to list of {name, content}
    rules_list = bundle.rules

    # Convert sub-agents — mark builtin vs custom
    sub_agents_list = []
    for a in bundle.agents:
        is_builtin = a.source_dir is not None and a.source_dir.resolve() == _SYSTEM_AGENTS_DIR
        is_all = a.tools == ["*"]
        agent_tools = [
            {
                "name": t_name,
                "enabled": is_all or t_name in a.tools,
                "desc": t_info.desc,
                "group": t_info.group,
            }
            for t_name, t_info in catalog.items()
        ]
        sub_agents_list.append(
            {
                "name": a.name,
                "desc": a.description,
                "tools": agent_tools,
                "system_prompt": a.system_prompt,
                "builtin": is_builtin,
            }
        )

    # Convert MCP servers
    mcps_list = [
        {
            "name": name,
            "command": srv.command or "",
            "args": srv.args,
            "env": srv.env,
            "disabled": srv.disabled,
        }
        for name, srv in bundle.mcp.items()
    ]

    member_id = member_dir.name
    return {
        "id": member_id,
        "name": agent.name,
        "description": agent.description,
        "model": agent.model,
        "status": meta.get("status", "draft"),
        "version": meta.get("version", "0.1.0"),
        "avatar_url": avatar_url(member_id, (avatars_dir() / f"{member_id}.png").exists()),
        "config": {
            "prompt": agent.system_prompt,
            "rules": rules_list,
            "tools": tools_list,
            "mcps": mcps_list,
            "skills": skills_list,
            "subAgents": sub_agents_list,
        },
        "created_at": meta.get("created_at", 0),
        "updated_at": meta.get("updated_at", 0),
    }


def _tools_from_repo(config: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = _load_tools_catalog()
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    enabled_tools = config.get("tools") or ["*"]
    is_all = enabled_tools == ["*"]
    tools_list = []
    for tool_name, tool_info in catalog.items():
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
        name = filename[:-3] if filename.endswith(".md") else filename
        rules.append({"name": name, "content": row.get("content", "")})
    return rules


def _sub_agents_from_repo(agent_config_id: str, agent_config_repo: Any) -> list[dict[str, Any]]:
    catalog = _load_tools_catalog()
    sub_agents = []
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
            for name, info in catalog.items()
        ]
        sub_agents.append(
            {
                "name": row["name"],
                "desc": row.get("description", ""),
                "tools": tools,
                "system_prompt": row.get("system_prompt", ""),
                "builtin": False,
            }
        )
    return sub_agents


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


def _member_from_repos(user: Any, agent_config_repo: Any) -> dict[str, Any]:
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
        },
        "created_at": config.get("created_at", 0),
        "updated_at": config.get("updated_at", 0),
    }


def _resolve_repo_backed_agent(member_id: str, user_repo: Any, agent_config_repo: Any) -> tuple[Any, dict[str, Any]] | None:
    user = user_repo.get_by_id(member_id)
    if user is None or user.agent_config_id is None:
        return None
    config = agent_config_repo.get_config(user.agent_config_id)
    if config is None:
        raise RuntimeError(f"Agent config {user.agent_config_id} is missing for {member_id}")
    return user, config


# ── Leon builtin ──


def _leon_builtin() -> dict[str, Any]:
    """Build Leon builtin member dict with full tool catalog."""
    catalog = _load_tools_catalog()
    tools = [{"name": k, "enabled": v.default, "desc": v.desc, "group": v.group} for k, v in catalog.items()]
    # Load built-in sub-agents (read-only display)
    builtin_agents = _load_builtin_agents(catalog)

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


def list_members(owner_user_id: str | None = None, user_repo: Any = None, agent_config_repo: Any = None) -> list[dict[str, Any]]:
    """List agent members. If owner_user_id given, only that user's agents (no builtin Leon).

    Args:
        owner_user_id: Filter to agents owned by this user.
        user_repo: Injected UserRepo for agent ownership lookup.
    """
    # @@@auth-scope — scoped by owner from DB, config from filesystem
    if owner_user_id:
        if user_repo is None or agent_config_repo is None:
            raise RuntimeError("user_repo and agent_config_repo are required when owner_user_id is provided")
        agents = user_repo.list_by_owner_user_id(owner_user_id)
        return [_member_from_repos(agent, agent_config_repo) for agent in agents]

    # Unscoped legacy path is now builtin-only. Owner-scoped callers must use repos.
    return [_leon_builtin()]


def get_member(member_id: str, *, user_repo: Any = None, agent_config_repo: Any = None) -> dict[str, Any] | None:
    if member_id == "__leon__":
        return _leon_builtin()
    if user_repo is None or agent_config_repo is None:
        raise RuntimeError("user_repo and agent_config_repo are required for agent member reads")
    user = user_repo.get_by_id(member_id)
    if user is None:
        return None
    return _member_from_repos(user, agent_config_repo)


def create_member(
    name: str,
    description: str = "",
    owner_user_id: str | None = None,
    user_repo: Any = None,
    agent_config_repo: Any = None,
) -> dict[str, Any]:
    from storage.contracts import UserRow, UserType
    from storage.utils import generate_agent_config_id, generate_member_id

    now = time.time()
    now_ms = int(now * 1000)
    agent_user_id = generate_member_id()
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

    return get_member(agent_user_id, user_repo=user_repo, agent_config_repo=agent_config_repo)  # type: ignore


def update_member(
    member_id: str,
    user_repo: Any = None,
    agent_config_repo: Any = None,
    **fields: Any,
) -> dict[str, Any] | None:
    if member_id == "__leon__":
        raise RuntimeError("Builtin agent is read-only")
    # @@@repo-first-member-writes - repo-backed agent users are the live contract now.
    # A leftover member dir must not silently take write precedence.
    repo_target = None
    if user_repo is not None and agent_config_repo is not None:
        repo_target = _resolve_repo_backed_agent(member_id, user_repo, agent_config_repo)
    if repo_target is not None:
        user, config = repo_target
        allowed = {"name", "description", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return get_member(member_id, user_repo=user_repo, agent_config_repo=agent_config_repo)
        if "name" in updates:
            user_repo.update(member_id, display_name=updates["name"])
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
        return get_member(member_id, user_repo=user_repo, agent_config_repo=agent_config_repo)
    member_dir = MEMBERS_DIR / member_id
    if not member_dir.is_dir():
        if user_repo is None or agent_config_repo is None:
            return None
        repo_target = _resolve_repo_backed_agent(member_id, user_repo, agent_config_repo)
        if repo_target is None:
            return None
        user, config = repo_target
        allowed = {"name", "description", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return get_member(member_id, user_repo=user_repo, agent_config_repo=agent_config_repo)
        if "name" in updates:
            user_repo.update(member_id, display_name=updates["name"])
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
        return get_member(member_id, user_repo=user_repo, agent_config_repo=agent_config_repo)
    allowed = {"name", "description", "status"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_member(member_id, user_repo=user_repo, agent_config_repo=agent_config_repo)
    if "status" in updates:
        meta = _read_json(member_dir / "meta.json", {})
        meta["status"] = updates["status"]
        meta["updated_at"] = int(time.time() * 1000)
        _write_json(member_dir / "meta.json", meta)
    if "name" in updates or "description" in updates:
        parsed = _parse_agent_md(member_dir / "agent.md") or {}
        _write_agent_md(
            member_dir / "agent.md",
            name=updates.get("name", parsed.get("name", "")),
            description=updates.get("description", parsed.get("description", "")),
            model=parsed.get("model"),
            tools=parsed.get("tools"),
            system_prompt=parsed.get("system_prompt", ""),
        )
        meta = _read_json(member_dir / "meta.json", {})
        meta["updated_at"] = int(time.time() * 1000)
        _write_json(member_dir / "meta.json", meta)

        if "name" in updates:
            if user_repo is None:
                raise RuntimeError("user_repo is required to update member name")
            user_repo.update(member_id, display_name=updates["name"])

    if member_id != "__leon__" and user_repo is not None and agent_config_repo is not None:
        user = user_repo.get_by_id(member_id)
        if user is None or user.agent_config_id is None:
            raise RuntimeError(f"Agent user {member_id} is missing agent_config_id")
        config = agent_config_repo.get_config(user.agent_config_id)
        if config is None:
            raise RuntimeError(f"Agent config {user.agent_config_id} is missing for {member_id}")
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

    return get_member(member_id, user_repo=user_repo, agent_config_repo=agent_config_repo)


def update_member_config(
    member_id: str,
    config_patch: dict[str, Any],
    user_repo: Any = None,
    agent_config_repo: Any = None,
) -> dict[str, Any] | None:
    if member_id == "__leon__":
        raise RuntimeError("Builtin agent is read-only")
    if user_repo is not None and agent_config_repo is not None:
        repo_target = _resolve_repo_backed_agent(member_id, user_repo, agent_config_repo)
        if repo_target is not None:
            return _sync_member_patch_to_repo(member_id, config_patch, user_repo, agent_config_repo)
    member_dir = MEMBERS_DIR / member_id
    if not member_dir.is_dir():
        if user_repo is None or agent_config_repo is None:
            return None
        return _sync_member_patch_to_repo(member_id, config_patch, user_repo, agent_config_repo)

    # prompt → agent.md body
    if "prompt" in config_patch and config_patch["prompt"] is not None:
        parsed = _parse_agent_md(member_dir / "agent.md") or {}
        _write_agent_md(
            member_dir / "agent.md",
            name=parsed.get("name", ""),
            description=parsed.get("description", ""),
            model=parsed.get("model"),
            tools=parsed.get("tools"),
            system_prompt=config_patch["prompt"],
        )

    # rules → rules/ directory
    if "rules" in config_patch and config_patch["rules"] is not None:
        _write_rules(member_dir, config_patch["rules"])

    # subAgents → agents/ directory
    if "subAgents" in config_patch and config_patch["subAgents"] is not None:
        _write_sub_agents(member_dir, config_patch["subAgents"])

    # tools/skills → runtime.json
    _write_runtime_resources(member_dir, config_patch)

    # mcps → .mcp.json
    if "mcps" in config_patch and config_patch["mcps"] is not None:
        _write_mcps(member_dir, config_patch["mcps"])

    # Update timestamp
    meta = _read_json(member_dir / "meta.json", {})
    meta["updated_at"] = int(time.time() * 1000)
    _write_json(member_dir / "meta.json", meta)

    # Dual-write full state to Supabase repo
    if agent_config_repo:
        if user_repo is None:
            raise RuntimeError("user_repo is required when syncing member config to agent_config_repo")
        user = user_repo.get_by_id(member_id)
        if user is None or user.agent_config_id is None:
            raise RuntimeError(f"Agent user {member_id} is missing agent_config_id")
        try:
            bundle = AgentLoader().load_bundle(member_dir)
            _save_config_to_repo(
                agent_config_repo,
                user.agent_config_id,
                agent_user_id=user.id,
                name=bundle.agent.name,
                description=bundle.agent.description,
                model=bundle.agent.model,
                tools=bundle.agent.tools,
                system_prompt=bundle.agent.system_prompt,
                status=bundle.meta.get("status", "draft"),
                version=bundle.meta.get("version", "0.1.0"),
                created_at=bundle.meta.get("created_at", 0),
                updated_at=bundle.meta.get("updated_at", 0),
                runtime={k: {"enabled": v.enabled, "desc": v.desc} for k, v in bundle.runtime.items()},
                mcp={n: {"command": s.command, "args": s.args, "env": s.env, "disabled": s.disabled} for n, s in bundle.mcp.items()},
            )
            # Sync rules
            for rule in bundle.rules:
                agent_config_repo.save_rule(user.agent_config_id, f"{rule['name']}.md", rule.get("content", ""))
            # Sync sub-agents
            for agent_cfg in bundle.agents:
                if agent_cfg.source_dir and agent_cfg.source_dir.resolve() == _SYSTEM_AGENTS_DIR:
                    continue  # skip builtins
                agent_config_repo.save_sub_agent(
                    user.agent_config_id,
                    agent_cfg.name,
                    description=agent_cfg.description,
                    model=agent_cfg.model,
                    tools=agent_cfg.tools,
                    system_prompt=agent_cfg.system_prompt,
                )
            # Sync skills
            for skill in bundle.skills:
                skill_path = Path(skill.get("path", ""))
                skill_md = skill_path / "SKILL.md"
                content = skill_md.read_text(encoding="utf-8") if skill_md.exists() else ""
                agent_config_repo.save_skill(user.agent_config_id, skill["name"], content)
        except Exception:
            logger.warning("Failed to sync config to repo for member %s", member_id, exc_info=True)

    return get_member(member_id, user_repo=user_repo, agent_config_repo=agent_config_repo)


# ── Supabase repo dual-write helper ──


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


def _sync_member_patch_to_repo(member_id: str, config_patch: dict[str, Any], user_repo: Any, agent_config_repo: Any) -> dict[str, Any]:
    # @@@repo-only-agent-shell - fresh register now creates DB-only agents. Owner-scoped
    # panel edits must keep working even when no legacy member dir exists.
    user = user_repo.get_by_id(member_id)
    if user is None or user.agent_config_id is None:
        raise RuntimeError(f"Agent user {member_id} is missing agent_config_id")
    current_config = agent_config_repo.get_config(user.agent_config_id)
    if current_config is None:
        raise RuntimeError(f"Agent config {user.agent_config_id} is missing for {member_id}")

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
        "mcp": _mcp_from_patch(config_patch, current_config),
    }
    agent_config_repo.save_config(user.agent_config_id, updated_config)
    _sync_repo_children(user.agent_config_id, config_patch, agent_config_repo)
    return get_member(member_id, user_repo=user_repo, agent_config_repo=agent_config_repo)


# ── Write helpers for config fields → file structure ──


def _write_rules(member_dir: Path, rules: list[dict[str, str]]) -> None:
    """Write rules list to rules/ directory. Replaces all existing rules."""
    rules_dir = member_dir / "rules"
    if rules_dir.exists():
        shutil.rmtree(rules_dir)
    if not rules:
        return
    rules_dir.mkdir(exist_ok=True)
    for rule in rules:
        if isinstance(rule, dict) and rule.get("name"):
            name = rule["name"].replace("/", "_").replace("\\", "_")
            (rules_dir / f"{name}.md").write_text(rule.get("content", ""), encoding="utf-8")


def _write_sub_agents(member_dir: Path, agents: list[dict[str, Any]]) -> None:
    """Write sub-agents list to agents/ directory."""
    from backend.web.services.library_service import get_library_agent_desc

    agents_dir = member_dir / "agents"
    if agents_dir.exists():
        shutil.rmtree(agents_dir)
    if not agents:
        return
    agents_dir.mkdir(exist_ok=True)
    for item in agents:
        if not (isinstance(item, dict) and item.get("name")):
            continue
        if item.get("builtin"):
            continue
        desc = item.get("desc", "")
        if not desc:
            desc = get_library_agent_desc(item["name"])
        # Convert CrudItem[] tools back to string list
        raw_tools = item.get("tools")
        tools: list[str] | None = None
        if isinstance(raw_tools, list) and raw_tools and isinstance(raw_tools[0], dict):
            enabled = [t["name"] for t in raw_tools if t.get("enabled")]
            tools = ["*"] if len(enabled) == len(raw_tools) else enabled
        elif isinstance(raw_tools, list):
            tools = raw_tools  # already string list
        _write_agent_md(
            agents_dir / f"{item['name']}.md",
            name=item["name"],
            description=desc,
            tools=tools,
            system_prompt=item.get("system_prompt", ""),
        )


def _write_runtime_resources(member_dir: Path, config_patch: dict[str, Any]) -> None:
    """Write tools/skills enabled+desc to runtime.json."""
    has_tools = "tools" in config_patch and config_patch["tools"] is not None
    has_skills = "skills" in config_patch and config_patch["skills"] is not None
    if not has_tools and not has_skills:
        return

    runtime = _read_json(member_dir / "runtime.json", {})

    # Clear old entries of the type being updated
    if has_tools:
        runtime = {k: v for k, v in runtime.items() if not k.startswith("tools:")}
        for item in config_patch["tools"]:
            if isinstance(item, dict) and item.get("name"):
                runtime[f"tools:{item['name']}"] = {
                    "enabled": item.get("enabled", True),
                    "desc": item.get("desc", ""),
                }

    if has_skills:
        runtime = {k: v for k, v in runtime.items() if not k.startswith("skills:")}
        for item in config_patch["skills"]:
            if isinstance(item, dict) and item.get("name"):
                runtime[f"skills:{item['name']}"] = {
                    "enabled": item.get("enabled", True),
                    "desc": item.get("desc", ""),
                }

    _write_json(member_dir / "runtime.json", runtime)


def _write_mcps(member_dir: Path, mcps: list[dict[str, Any]]) -> None:
    """Write MCP list to .mcp.json. New assignments (no command) copy from Library."""
    from backend.web.services.library_service import get_mcp_server_config

    servers: dict[str, Any] = {}
    for item in mcps:
        if isinstance(item, dict) and item.get("name"):
            if item.get("command"):
                # Existing/customized — write as-is
                servers[item["name"]] = {
                    "command": item["command"],
                    "args": item.get("args", []),
                    "env": item.get("env", {}),
                    "disabled": item.get("disabled", False),
                }
            else:
                # New assignment from Library — copy config
                lib_cfg = get_mcp_server_config(item["name"])
                if lib_cfg:
                    servers[item["name"]] = {
                        "command": lib_cfg.get("command", ""),
                        "args": lib_cfg.get("args", []),
                        "env": lib_cfg.get("env", {}),
                        "disabled": item.get("disabled", False),
                    }
                else:
                    servers[item["name"]] = {
                        "command": "",
                        "args": [],
                        "env": {},
                        "disabled": item.get("disabled", False),
                    }
    if servers:
        _write_json(member_dir / ".mcp.json", {"mcpServers": servers})
    else:
        mcp_path = member_dir / ".mcp.json"
        if mcp_path.exists():
            mcp_path.unlink()


# ── Publish / Delete ──


def publish_member(member_id: str, bump_type: str = "patch", user_repo: Any = None, agent_config_repo: Any = None) -> dict[str, Any] | None:
    member_dir = MEMBERS_DIR / member_id
    user = None
    config = None
    if user_repo is not None:
        user = user_repo.get_by_id(member_id)
    if agent_config_repo and user is not None and user.agent_config_id is not None:
        config = agent_config_repo.get_config(user.agent_config_id)
    if not member_dir.is_dir() and config is None:
        return None

    meta = _read_json(member_dir / "meta.json", {}) if member_dir.is_dir() else {}
    current_version = meta.get("version") or (config or {}).get("version", "0.1.0")
    parts = current_version.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if bump_type == "major":
        major, minor, patch = major + 1, 0, 0
    elif bump_type == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    meta["version"] = f"{major}.{minor}.{patch}"
    meta["status"] = "active"
    meta["updated_at"] = int(time.time() * 1000)
    if member_dir.is_dir():
        _write_json(member_dir / "meta.json", meta)

    # Dual-write publish status to Supabase repo
    if agent_config_repo:
        if user_repo is None:
            raise RuntimeError("user_repo is required when publishing member config to agent_config_repo")
        if user is None or user.agent_config_id is None:
            raise RuntimeError(f"Agent user {member_id} is missing agent_config_id")
        try:
            if config:
                agent_config_repo.save_config(
                    user.agent_config_id,
                    {
                        **config,
                        "version": meta["version"],
                        "status": "active",
                        "updated_at": meta["updated_at"],
                    },
                )
        except Exception:
            logger.warning("Failed to update repo for publish of %s", member_id, exc_info=True)

    return get_member(member_id, user_repo=user_repo, agent_config_repo=agent_config_repo)


def delete_member(member_id: str, user_repo: Any = None, agent_config_repo: Any = None) -> bool:
    if member_id == "__leon__":
        return False
    member_dir = MEMBERS_DIR / member_id
    user = user_repo.get_by_id(member_id) if user_repo is not None else None
    if not member_dir.is_dir() and user is None:
        return False

    # Delete from Supabase repo before removing filesystem
    if agent_config_repo:
        if user_repo is None:
            raise RuntimeError("user_repo is required when deleting member config from agent_config_repo")
        if user is None or user.agent_config_id is None:
            raise RuntimeError(f"Agent user {member_id} is missing agent_config_id")
        try:
            agent_config_repo.delete_config(user.agent_config_id)
        except Exception:
            logger.warning("Failed to delete config from repo for %s", member_id, exc_info=True)

    if member_dir.is_dir():
        shutil.rmtree(member_dir)

    # Also remove from unified users table
    if user_repo is None:
        raise RuntimeError("user_repo is required to delete member")
    user_repo.delete(member_id)

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
    from storage.utils import generate_agent_config_id, generate_member_id

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
        user_id = generate_member_id()
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

    # @@@snapshot-install-repo-only - marketplace member installs no longer materialize
    # a member dir. The DB is now the live shell; marketplace lineage still needs
    # a separate repo-rooted home because publish used to read meta.json.source.
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
