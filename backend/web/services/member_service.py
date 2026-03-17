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
import shutil
import time
from pathlib import Path
from typing import Any

import yaml

from config.defaults.tool_catalog import TOOLS_BY_NAME, ToolDef
from config.loader import AgentLoader

logger = logging.getLogger(__name__)

LEON_HOME = Path.home() / ".leon"
MEMBERS_DIR = LEON_HOME / "members"
_SYSTEM_AGENTS_DIR = (Path(__file__).resolve().parents[3] / "config" / "defaults" / "agents").resolve()


def _load_tools_catalog() -> dict[str, ToolDef]:
    """Return the typed tool catalog (name → ToolDef)."""
    return TOOLS_BY_NAME


def ensure_members_dir() -> None:
    MEMBERS_DIR.mkdir(parents=True, exist_ok=True)


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


def _write_agent_md(path: Path, name: str, description: str = "",
                    model: str | None = None, tools: list[str] | None = None,
                    system_prompt: str = "") -> None:
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
        sub_agents_list.append({
            "name": a.name,
            "desc": a.description,
            "tools": agent_tools,
            "system_prompt": a.system_prompt,
            "builtin": is_builtin,
        })

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

    return {
        "id": member_dir.name,
        "name": agent.name,
        "description": agent.description,
        "model": agent.model,
        "status": meta.get("status", "draft"),
        "version": meta.get("version", "0.1.0"),
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


# ── Leon builtin ──

def _leon_builtin() -> dict[str, Any]:
    """Build Leon builtin member dict with full tool catalog."""
    catalog = _load_tools_catalog()
    tools = [{"name": k, "enabled": v.default, "desc": v.desc, "group": v.group} for k, v in catalog.items()]
    # Load built-in sub-agents (read-only display)
    builtin_agents = _load_builtin_agents(catalog)

    return {
        "id": "__leon__",
        "name": "Leon",
        "description": "通用数字成员，随时准备为你工作",
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
                    {"name": k, "enabled": is_all or k in ac.tools, "desc": v.desc, "group": v.group}
                    for k, v in catalog.items()
                ]
                agents.append({
                    "name": ac.name, "desc": ac.description,
                    "tools": agent_tools, "system_prompt": ac.system_prompt, "builtin": True,
                })
    return agents


def _ensure_leon_dir() -> Path:
    """Ensure Leon's member directory exists for persisting edits."""
    leon_dir = MEMBERS_DIR / "__leon__"
    leon_dir.mkdir(parents=True, exist_ok=True)
    if not (leon_dir / "agent.md").exists():
        _write_agent_md(leon_dir / "agent.md", name="Leon",
                        description="通用数字成员，随时准备为你工作")
    if not (leon_dir / "meta.json").exists():
        _write_json(leon_dir / "meta.json", {
            "status": "active", "version": "1.0.0",
            "created_at": 0, "updated_at": 0,
        })
    return leon_dir


# ── CRUD operations ──

def list_members(owner_id: str | None = None) -> list[dict[str, Any]]:
    """List agent members. If owner_id given, only that user's agents (no builtin Leon)."""
    # @@@auth-scope — scoped by owner from DB, config from filesystem
    if owner_id:
        from storage.providers.sqlite.member_repo import SQLiteMemberRepo
        repo = SQLiteMemberRepo()
        try:
            agents = repo.list_by_owner(owner_id)
        finally:
            repo.close()
        results = []
        for agent in agents:
            agent_dir = MEMBERS_DIR / agent.id
            if agent_dir.is_dir() and (agent_dir / "agent.md").exists():
                item = _member_to_dict(agent_dir)
                if item:
                    results.append(item)
        return results

    # Unscoped: return all (legacy/unauthenticated)
    leon = get_member("__leon__")
    results: list[dict[str, Any]] = [leon] if leon else [_leon_builtin()]
    if MEMBERS_DIR.exists():
        for d in sorted(MEMBERS_DIR.iterdir(), reverse=True):
            if d.is_dir() and d.name != "__leon__" and (d / "agent.md").exists():
                item = _member_to_dict(d)
                if item:
                    results.append(item)
    return results


def get_member(member_id: str) -> dict[str, Any] | None:
    if member_id == "__leon__":
        leon_dir = MEMBERS_DIR / "__leon__"
        if leon_dir.is_dir() and (leon_dir / "agent.md").exists():
            item = _member_to_dict(leon_dir)
            if item:
                item["builtin"] = True
                return item
        return _leon_builtin()
    member_dir = MEMBERS_DIR / member_id
    if not member_dir.is_dir():
        return None
    return _member_to_dict(member_dir)


def create_member(name: str, description: str = "") -> dict[str, Any]:
    now = int(time.time() * 1000)
    member_id = str(now)
    member_dir = MEMBERS_DIR / member_id
    member_dir.mkdir(parents=True, exist_ok=True)
    _write_agent_md(member_dir / "agent.md", name=name, description=description)
    _write_json(member_dir / "meta.json", {
        "status": "draft", "version": "0.1.0",
        "created_at": now, "updated_at": now,
    })
    return get_member(member_id)  # type: ignore


def update_member(member_id: str, **fields: Any) -> dict[str, Any] | None:
    if member_id == "__leon__":
        member_dir = _ensure_leon_dir()
    else:
        member_dir = MEMBERS_DIR / member_id
        if not member_dir.is_dir():
            return None
    allowed = {"name", "description", "status"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_member(member_id)
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
    return get_member(member_id)


def update_member_config(member_id: str, config_patch: dict[str, Any]) -> dict[str, Any] | None:
    if member_id == "__leon__":
        member_dir = _ensure_leon_dir()
    else:
        member_dir = MEMBERS_DIR / member_id
        if not member_dir.is_dir():
            return None

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
    return get_member(member_id)


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
            (rules_dir / f"{name}.md").write_text(
                rule.get("content", ""), encoding="utf-8"
            )


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
                        "command": "", "args": [], "env": {},
                        "disabled": item.get("disabled", False),
                    }
    if servers:
        _write_json(member_dir / ".mcp.json", {"mcpServers": servers})
    else:
        mcp_path = member_dir / ".mcp.json"
        if mcp_path.exists():
            mcp_path.unlink()


# ── Publish / Delete ──

def publish_member(member_id: str, bump_type: str = "patch") -> dict[str, Any] | None:
    member_dir = MEMBERS_DIR / member_id
    if not member_dir.is_dir():
        return None
    meta = _read_json(member_dir / "meta.json", {})
    parts = meta.get("version", "0.1.0").split(".")
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
    _write_json(member_dir / "meta.json", meta)
    return get_member(member_id)


def delete_member(member_id: str) -> bool:
    if member_id == "__leon__":
        return False
    member_dir = MEMBERS_DIR / member_id
    if not member_dir.is_dir():
        return False
    shutil.rmtree(member_dir)
    return True
