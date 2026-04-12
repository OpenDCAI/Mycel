"""Unified agent & runtime configuration loader.

Combines:
- Three-tier runtime config merge (system > user > project) — for default agent
- Agent .md parsing (YAML frontmatter + system prompt)
- Bundle discovery (meta.json, rules/, agents/, skills/, .mcp.json, runtime.json)

Configuration priority (highest to lowest):
1. CLI overrides
2. Project config (.leon/runtime.json in workspace)
3. User config (~/.leon/runtime.json)
4. System defaults (config/defaults/runtime.json)

Bundle loading: explicit bundle path or repo-backed agent_config_id only.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from config.schema import LeonSettings
from config.types import (
    AgentBundle,
    AgentConfig,
    McpServerConfig,
    RuntimeResourceConfig,
)
from config.user_paths import remap_default_user_home_string, user_home_path, user_home_read_candidates

logger = logging.getLogger(__name__)


class AgentLoader:
    """Unified loader for runtime config, agent definitions, and agent bundles."""

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self._system_defaults_dir = Path(__file__).parent / "defaults"
        self._agents: dict[str, AgentConfig] = {}

    # ── Three-tier runtime config (unchanged) ──

    def load(self, cli_overrides: dict[str, Any] | None = None) -> LeonSettings:
        """Load runtime configuration with three-tier merge."""
        system_config = self._load_system_defaults()
        user_config = self._load_user_config()
        project_config = self._load_project_config()

        # Deep merge: runtime, memory, tools
        merged_runtime = self._deep_merge(
            system_config.get("runtime", {}),
            user_config.get("runtime", {}),
            project_config.get("runtime", {}),
        )

        merged_memory = self._deep_merge(
            system_config.get("memory", {}),
            user_config.get("memory", {}),
            project_config.get("memory", {}),
        )
        merged_tools = self._deep_merge(
            system_config.get("tools", {}),
            user_config.get("tools", {}),
            project_config.get("tools", {}),
        )

        # Lookup strategy for mcp/skills (first found wins)
        merged_mcp = self._lookup_merge("mcp", project_config, user_config, system_config)
        merged_skills = self._lookup_merge("skills", project_config, user_config, system_config)

        system_prompt = project_config.get("system_prompt") or user_config.get("system_prompt") or system_config.get("system_prompt")

        final_config: dict[str, Any] = {
            "runtime": merged_runtime,
            "memory": merged_memory,
            "tools": merged_tools,
            "mcp": merged_mcp,
            "skills": merged_skills,
            "system_prompt": system_prompt,
        }

        if cli_overrides:
            final_config = self._deep_merge(final_config, cli_overrides)

        final_config = self._expand_env_vars(final_config)
        self._ensure_default_skill_dir(final_config)
        final_config = self._remove_none_values(final_config)

        return LeonSettings(**final_config)

    # ── Agent .md parsing (merged from core/task/loader) ──

    def load_runtime_agents(self) -> dict[str, AgentConfig]:
        """Load runtime-facing agent definitions."""
        self._load_agent_layers()
        return self._agents

    def _load_agent_layers(self) -> None:
        self._agents = {}

        # 1. Built-in agents (lowest priority)
        self._load_agents_from_dir(self._system_defaults_dir / "agents")

        # 2. User-level agents
        for path in user_home_read_candidates("agents"):
            self._load_agents_from_dir(path)

        # 3. Project-level agents
        if self.workspace_root:
            self._load_agents_from_dir(self.workspace_root / ".leon" / "agents")

    def _load_agents_from_dir(self, dir_path: Path) -> None:
        """Load all .md files from a directory."""
        if not dir_path.exists():
            return
        for md_file in dir_path.glob("*.md"):
            config = self.parse_agent_file(md_file)
            if config:
                self._agents[config.name] = config

    @staticmethod
    def parse_agent_file(path: Path) -> AgentConfig | None:
        """Parse Markdown file with YAML frontmatter into AgentConfig."""
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

        return AgentConfig(
            name=fm["name"],
            description=fm.get("description", ""),
            tools=fm.get("tools", ["*"]),
            system_prompt=parts[2].strip(),
            model=fm.get("model"),
            source_dir=None,
        )

    def get_agent(self, name: str) -> AgentConfig | None:
        """Get a specific agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> list[str]:
        """List all available agent names."""
        return list(self._agents.keys())

    # ── Bundle discovery ──

    def load_bundle(self, agent_dir: Path) -> AgentBundle:
        """Load a complete agent bundle from a directory.

        Used by explicit bundle_dir startup and repo-backed agent_config snapshots.
        Sub-agents use two-layer merge: system defaults → bundle-specific (override by name).
        """
        agent_dir = agent_dir.resolve()
        agent = self.parse_agent_file(agent_dir / "agent.md")
        if not agent:
            raise ValueError(f"No valid agent.md in {agent_dir}")

        return AgentBundle(
            agent=agent,
            meta=self._discover_meta(agent_dir),
            runtime=self._discover_runtime(agent_dir),
            rules=self._discover_rules(agent_dir),
            agents=self._merge_agents(agent_dir),
            skills=self._discover_skills(agent_dir),
            mcp=self._discover_mcp(agent_dir),
        )

    @staticmethod
    def _discover_meta(agent_dir: Path) -> dict[str, Any]:
        """Read meta.json."""
        path = agent_dir / "meta.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _discover_runtime(agent_dir: Path) -> dict[str, RuntimeResourceConfig]:
        """Read runtime.json → {resource_name: RuntimeResourceConfig}."""
        path = agent_dir / "runtime.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        result: dict[str, RuntimeResourceConfig] = {}
        for name, cfg in data.items():
            if isinstance(cfg, dict):
                result[name] = RuntimeResourceConfig(**cfg)
        return result

    @staticmethod
    def _discover_rules(agent_dir: Path) -> list[dict[str, str]]:
        """Scan rules/*.md → [{name, content}]."""
        rules_dir = agent_dir / "rules"
        if not rules_dir.is_dir():
            return []
        rules = []
        for md in sorted(rules_dir.glob("*.md")):
            try:
                content = md.read_text(encoding="utf-8")
            except OSError:
                continue
            rules.append({"name": md.stem, "content": content})
        return rules

    def _merge_agents(self, agent_dir: Path) -> list[AgentConfig]:
        """Two-layer merge: system defaults → member-specific (override by name)."""
        merged: dict[str, AgentConfig] = {}

        # Layer 1: system built-in agents
        for agent in self._discover_agents(self._system_defaults_dir):
            merged[agent.name] = agent

        # Layer 2: member-specific agents (override by name)
        for agent in self._discover_agents(agent_dir):
            merged[agent.name] = agent

        return list(merged.values())

    @staticmethod
    def _discover_agents(agent_dir: Path) -> list[AgentConfig]:
        """Scan agents/*.md → [AgentConfig]."""
        agents_dir = agent_dir / "agents"
        if not agents_dir.is_dir():
            return []
        agents = []
        for md in sorted(agents_dir.glob("*.md")):
            config = AgentLoader.parse_agent_file(md)
            if config:
                agents.append(config)
        return agents

    @staticmethod
    def _discover_skills(agent_dir: Path) -> list[dict[str, Any]]:
        """Scan skills/*/SKILL.md → [{name, path}]."""
        skills_dir = agent_dir / "skills"
        if not skills_dir.is_dir():
            return []
        skills = []
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                skills.append({"name": skill_dir.name, "path": str(skill_dir)})
            elif any(skill_dir.glob("*.md")):
                # Fallback: any .md in skill dir
                skills.append({"name": skill_dir.name, "path": str(skill_dir)})
        return skills

    @staticmethod
    def _discover_mcp(agent_dir: Path) -> dict[str, McpServerConfig]:
        """Read .mcp.json → {server_name: McpServerConfig}."""
        path = agent_dir / ".mcp.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        # .mcp.json has {"mcpServers": {...}} or flat {...}
        servers = data.get("mcpServers", data)
        if not isinstance(servers, dict):
            return {}
        result: dict[str, McpServerConfig] = {}
        for name, cfg in servers.items():
            if isinstance(cfg, dict):
                result[name] = McpServerConfig(**{k: v for k, v in cfg.items() if k in McpServerConfig.model_fields})
        return result

    # ── Internal helpers ──

    def _load_system_defaults(self) -> dict[str, Any]:
        """Load system defaults from runtime.json."""
        return self._load_json(self._system_defaults_dir / "runtime.json")

    def _load_user_config(self) -> dict[str, Any]:
        """Load user config from ~/.leon/runtime.json."""
        merged: dict[str, Any] = {}
        for path in user_home_read_candidates("runtime.json"):
            merged = self._deep_merge(merged, self._load_json(path))
        return merged

    def _load_project_config(self) -> dict[str, Any]:
        """Load project config from .leon/runtime.json."""
        if not self.workspace_root:
            return {}
        return self._load_json(self.workspace_root / ".leon" / "runtime.json")

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _deep_merge(self, *dicts: dict[str, Any]) -> dict[str, Any]:
        """Deep merge multiple dictionaries. Later dicts override earlier ones."""
        result: dict[str, Any] = {}
        for d in dicts:
            for key, value in d.items():
                if key not in result:
                    result[key] = value
                elif value is None:
                    continue
                elif isinstance(value, dict) and isinstance(result[key], dict):
                    result[key] = self._deep_merge(result[key], value)
                else:
                    result[key] = value
        return result

    def _lookup_merge(self, key: str, *configs: dict[str, Any]) -> Any:
        """Lookup strategy: first found wins."""
        for config in configs:
            if key in config and config[key] is not None:
                return config[key]
        return {}

    def _expand_env_vars(self, obj: Any) -> Any:
        """Recursively expand ${VAR} and ~ in string values."""
        if isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._expand_env_vars(v) for v in obj]
        if isinstance(obj, str):
            return remap_default_user_home_string(obj)
        return obj

    def _remove_none_values(self, obj: Any) -> Any:
        """Recursively remove None values to allow Pydantic defaults."""
        if isinstance(obj, dict):
            return {k: self._remove_none_values(v) for k, v in obj.items() if v is not None}
        if isinstance(obj, list):
            return [self._remove_none_values(v) for v in obj if v is not None]
        return obj

    def _ensure_default_skill_dir(self, config: dict[str, Any]) -> None:
        """Create ~/.leon/skills when configured, so first-run validation succeeds."""
        skills = config.get("skills")
        if not isinstance(skills, dict):
            return
        paths = skills.get("paths")
        if not isinstance(paths, list):
            return
        default_home_skills = user_home_path("skills")
        for raw_path in paths:
            if not isinstance(raw_path, str):
                continue
            path = Path(raw_path).expanduser()
            # @@@tmp-home-normalization - macOS maps /tmp -> /private/tmp, so compare normalized paths before bootstrap.
            if path.resolve() == default_home_skills.resolve() and not path.exists():
                path.mkdir(parents=True, exist_ok=True)


def load_config(
    workspace_root: str | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> LeonSettings:
    """Convenience function to load runtime configuration."""
    return AgentLoader(workspace_root=workspace_root).load(cli_overrides=cli_overrides)


def load_bundle_from_repo(agent_config_repo: Any, agent_config_id: str) -> AgentBundle | None:
    """Load agent bundle from Supabase agent_config tables keyed by agent_config_id."""
    config = agent_config_repo.get_config(agent_config_id)
    if not config:
        return None

    # Parse agent identity from config
    agent = AgentConfig(
        name=config.get("name", ""),
        description=config.get("description", ""),
        tools=config.get("tools", ["*"]),
        system_prompt=config.get("system_prompt", ""),
        model=config.get("model"),
        source_dir=None,
    )

    meta = dict(config.get("meta") if isinstance(config.get("meta"), dict) else {})
    meta.update(
        {
            "status": config.get("status", "draft"),
            "version": config.get("version", "0.1.0"),
            "created_at": config.get("created_at", 0),
            "updated_at": config.get("updated_at", 0),
        }
    )

    # Runtime from config
    runtime_data = config.get("runtime") or {}
    runtime = {}
    for rname, rcfg in runtime_data.items():
        if isinstance(rcfg, dict):
            runtime[rname] = RuntimeResourceConfig(**rcfg)

    # Rules from agent_rules table
    rule_rows = agent_config_repo.list_rules(agent_config_id)
    rules = [{"name": r.get("filename", "").replace(".md", ""), "content": r.get("content", "")} for r in rule_rows]

    # Sub-agents use the same default layer as filesystem bundles, then repo rows override by name.
    loader = AgentLoader()
    agents_by_name = {agent.name: agent for agent in loader._discover_agents(loader._system_defaults_dir)}
    sub_agent_rows = agent_config_repo.list_sub_agents(agent_config_id)
    for sa in sub_agent_rows:
        sub_agent = AgentConfig(
            name=sa.get("name", ""),
            description=sa.get("description", ""),
            tools=sa.get("tools", ["*"]),
            system_prompt=sa.get("system_prompt", ""),
            model=sa.get("model"),
            source_dir=None,
        )
        if sub_agent.name:
            agents_by_name[sub_agent.name] = sub_agent

    # Skills from agent_skills table
    skill_rows = agent_config_repo.list_skills(agent_config_id)
    skills = []
    for s in skill_rows:
        item = {"name": s.get("name", ""), "content": s.get("content", "")}
        if isinstance(s.get("meta_json"), dict):
            item["meta"] = s.get("meta_json")
        skills.append(item)

    # MCP from config
    mcp_data = config.get("mcp") or {}
    mcp = {}
    for mname, mcfg in mcp_data.items():
        if isinstance(mcfg, dict):
            mcp[mname] = McpServerConfig(**{k: v for k, v in mcfg.items() if k in McpServerConfig.model_fields})

    return AgentBundle(
        agent=agent,
        meta=meta,
        runtime=runtime,
        rules=rules,
        agents=list(agents_by_name.values()),
        skills=skills,
        mcp=mcp,
    )
