"""Unified agent & runtime configuration loader.

Combines:
- Three-tier runtime config merge (system > user > project) — for default agent
- Agent .md parsing (YAML frontmatter + system prompt)
- Local agent config discovery (agent.md, meta.json, runtime.json, rules/, agents/, skills/, .mcp.json)

Configuration priority (highest to lowest):
1. CLI overrides
2. Project config (.leon/runtime.json in workspace)
3. User config (~/.leon/runtime.json)
4. System defaults (config/defaults/runtime.json)

Local agent config loading is explicit path only. Repo-backed startup reads AgentConfig aggregates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from config.agent_config_resolver import resolve_agent_config
from config.agent_config_types import AgentConfig, AgentRule, AgentSkill, AgentSubAgent, McpServerConfig, ResolvedAgentConfig
from config.schema import LeonSettings
from config.skill_files import normalize_skill_file_entries
from config.types import RuntimeAgentDefinition
from config.user_paths import remap_default_user_home_string, user_home_path, user_home_read_candidates

logger = logging.getLogger(__name__)


class AgentLoader:
    """Unified loader for runtime config, agent definitions, and local agent configs."""

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self._system_defaults_dir = Path(__file__).parent / "defaults"
        self._agents: dict[str, RuntimeAgentDefinition] = {}

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

    def load_runtime_agents(self) -> dict[str, RuntimeAgentDefinition]:
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
    def parse_agent_file(path: Path, *, strict: bool = False) -> RuntimeAgentDefinition | None:
        """Parse Markdown file with YAML frontmatter into RuntimeAgentDefinition."""
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            if strict:
                raise RuntimeError(f"agent.md could not be read: {path}") from exc
            return None

        if not content.startswith("---"):
            if strict:
                raise ValueError(f"agent.md must start with YAML frontmatter: {path}")
            return None
        parts = content.split("---", 2)
        if len(parts) < 3:
            if strict:
                raise ValueError(f"agent.md frontmatter is not closed: {path}")
            return None

        try:
            fm = yaml.safe_load(parts[1])
        except yaml.YAMLError as exc:
            if strict:
                raise ValueError(f"agent.md frontmatter must be valid YAML: {path}") from exc
            return None

        if not isinstance(fm, dict):
            if strict:
                raise ValueError(f"agent.md frontmatter must be a mapping: {path}")
            return None
        name = fm.get("name")
        if not isinstance(name, str) or not name.strip():
            if strict:
                raise ValueError(f"agent.md frontmatter must include name: {path}")
            return None
        fm["name"] = name.strip()

        return RuntimeAgentDefinition(
            name=fm["name"],
            description=fm.get("description", ""),
            tools=fm.get("tools", ["*"]),
            system_prompt=parts[2].strip(),
            model=fm.get("model"),
        )

    def get_agent(self, name: str) -> RuntimeAgentDefinition | None:
        """Get a specific agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> list[str]:
        """List all available agent names."""
        return list(self._agents.keys())

    # ── Local agent config discovery ──

    def load_resolved_config_from_dir(self, agent_dir: Path) -> ResolvedAgentConfig:
        """Load a local agent config directory into runtime-ready resolved config.

        Sub-agents use two-layer merge: system defaults → local config (override by name).
        """
        agent_dir = agent_dir.resolve()
        agent = self.parse_agent_file(agent_dir / "agent.md", strict=True)
        if not agent:
            raise ValueError(f"No valid agent.md in {agent_dir}")

        config = AgentConfig(
            id=f"local:{agent_dir.name}",
            owner_user_id="local",
            agent_user_id="local",
            name=agent.name,
            description=agent.description,
            tools=agent.tools,
            system_prompt=agent.system_prompt,
            model=agent.model,
            runtime_settings=self._discover_runtime(agent_dir),
            meta=self._discover_meta(agent_dir),
            rules=self._discover_rules(agent_dir),
            sub_agents=self._merge_sub_agents(agent_dir),
            skills=self._discover_skills(agent_dir),
            mcp_servers=self._discover_mcp(agent_dir),
        )
        return resolve_agent_config(config)

    @staticmethod
    def _discover_meta(agent_dir: Path) -> dict[str, Any]:
        """Read meta.json."""
        path = agent_dir / "meta.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Local Agent metadata must be valid JSON: {path}") from exc
        except OSError as exc:
            raise RuntimeError(f"Local Agent metadata could not be read: {path}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Local Agent metadata must be a JSON object: {path}")
        return data

    @staticmethod
    def _discover_runtime(agent_dir: Path) -> dict[str, Any]:
        """Read runtime.json as runtime_settings."""
        path = agent_dir / "runtime.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Local runtime config must be valid JSON: {path}") from exc
        except OSError as exc:
            raise RuntimeError(f"Local runtime config could not be read: {path}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Local runtime config must be a JSON object: {path}")
        return data

    @staticmethod
    def _discover_rules(agent_dir: Path) -> list[AgentRule]:
        """Scan rules/*.md."""
        rules_dir = agent_dir / "rules"
        if not rules_dir.is_dir():
            return []
        rules: list[AgentRule] = []
        for md in sorted(rules_dir.glob("*.md")):
            try:
                content = md.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise RuntimeError(f"Local rule file could not be read: {md}") from exc
            rules.append(AgentRule(name=md.stem, content=content))
        return rules

    def _merge_sub_agents(self, agent_dir: Path) -> list[AgentSubAgent]:
        """Two-layer merge: system defaults → local config agents (override by name)."""
        merged: dict[str, RuntimeAgentDefinition] = {}

        # Layer 1: system built-in agents
        for agent in self._discover_agents(self._system_defaults_dir):
            merged[agent.name] = agent

        # Layer 2: repo/user agent configs (override by name)
        for agent in self._discover_agents(agent_dir, strict=True):
            merged[agent.name] = agent

        return [
            AgentSubAgent(
                name=agent.name,
                description=agent.description,
                model=agent.model,
                tools=agent.tools,
                system_prompt=agent.system_prompt,
            )
            for agent in merged.values()
        ]

    @staticmethod
    def _discover_agents(agent_dir: Path, *, strict: bool = False) -> list[RuntimeAgentDefinition]:
        """Scan agents/*.md -> [RuntimeAgentDefinition]."""
        agents_dir = agent_dir / "agents"
        if not agents_dir.is_dir():
            return []
        agents = []
        for md in sorted(agents_dir.glob("*.md")):
            config = AgentLoader.parse_agent_file(md, strict=strict)
            if config:
                agents.append(config)
        return agents

    @staticmethod
    def _discover_skills(agent_dir: Path) -> list[AgentSkill]:
        """Scan skills/*/SKILL.md."""
        skills_dir = agent_dir / "skills"
        if not skills_dir.is_dir():
            return []
        skills: list[AgentSkill] = []
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                raise ValueError(f"Local Skill directory must contain SKILL.md: {skill_dir}")
            content = skill_md.read_text(encoding="utf-8")
            metadata = AgentLoader._skill_frontmatter(content)
            file_entries: list[tuple[Path, str]] = []
            for file_path in sorted(skill_dir.rglob("*")):
                if not file_path.is_file() or file_path.name == "SKILL.md":
                    continue
                try:
                    file_entries.append((file_path.relative_to(skill_dir), file_path.read_text(encoding="utf-8")))
                except UnicodeDecodeError as exc:
                    raise RuntimeError(f"Local Skill adjacent file could not be read: {file_path}") from exc
            files = normalize_skill_file_entries(file_entries, context="Local Skill files")
            skills.append(
                AgentSkill(
                    name=str(metadata["name"]),
                    description=str(metadata.get("description") or ""),
                    content=content,
                    files=files,
                )
            )
        return skills

    @staticmethod
    def _skill_frontmatter(content: str) -> dict[str, Any]:
        if not content.startswith("---"):
            raise ValueError("Local Skill content must include frontmatter name")
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError("Local Skill content must include frontmatter name")
        try:
            metadata = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError as exc:
            raise ValueError("Local Skill frontmatter must be valid YAML") from exc
        if not isinstance(metadata, dict):
            raise ValueError("Local Skill frontmatter must be a mapping")
        name = metadata.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Local Skill content must include frontmatter name")
        metadata["name"] = name.strip()
        return metadata

    @staticmethod
    def _discover_mcp(agent_dir: Path) -> list[McpServerConfig]:
        """Read .mcp.json."""
        path = agent_dir / ".mcp.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Local MCP config must be valid JSON: {path}") from exc
        except OSError as exc:
            raise RuntimeError(f"Local MCP config could not be read: {path}") from exc
        # .mcp.json has {"mcpServers": {...}} or flat {...}
        servers = data.get("mcpServers", data)
        if not isinstance(servers, dict):
            raise ValueError(f"Local MCP config mcpServers must be an object: {path}")
        result: list[McpServerConfig] = []
        for name, cfg in servers.items():
            if not isinstance(cfg, dict):
                raise ValueError(f"Local MCP server config must be an object: {path}#{name}")
            fields = {k: v for k, v in cfg.items() if k in McpServerConfig.model_fields}
            fields["name"] = name
            if cfg.get("disabled") is True:
                fields["enabled"] = False
            result.append(McpServerConfig(**fields))
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
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Runtime config must be valid JSON: {path}") from exc
        except OSError as exc:
            raise RuntimeError(f"Runtime config could not be read: {path}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Runtime config must be a JSON object: {path}")
        return data

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
