"""Unified agent & runtime configuration loader.

Combines:
- System runtime defaults plus explicit call-site overrides
- Built-in runtime agent .md parsing (YAML frontmatter + system prompt)

Configuration priority (highest to lowest):
1. CLI overrides
2. System defaults (config/defaults/runtime.json)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from config.path_remap import remap_default_home_string
from config.schema import LeonSettings
from config.types import RuntimeAgentDefinition

logger = logging.getLogger(__name__)


class AgentLoader:
    """Unified loader for runtime config and runtime agent definitions."""

    def __init__(self):
        self._system_defaults_dir = Path(__file__).parent / "defaults"
        self._agents: dict[str, RuntimeAgentDefinition] = {}

    # ── Runtime config ──

    def load(self, cli_overrides: dict[str, Any] | None = None) -> LeonSettings:
        """Load runtime configuration from system defaults and explicit overrides."""
        system_config = self._load_system_defaults()
        self._reject_removed_runtime_key("skills", system_config, cli_overrides or {})

        final_config: dict[str, Any] = dict(system_config)

        if cli_overrides:
            final_config = self._deep_merge(final_config, cli_overrides)

        final_config = self._expand_env_vars(final_config)
        final_config = self._remove_none_values(final_config)

        return LeonSettings(**final_config)

    # ── Built-in runtime agent .md parsing ──

    def load_runtime_agents(self) -> dict[str, RuntimeAgentDefinition]:
        """Load runtime-facing agent definitions."""
        self._load_agent_layers()
        return self._agents

    def _load_agent_layers(self) -> None:
        self._agents = {}
        self._load_agents_from_dir(self._system_defaults_dir / "agents")

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

    # ── Internal helpers ──

    def _load_system_defaults(self) -> dict[str, Any]:
        """Load system defaults from runtime.json."""
        return self._load_json(self._system_defaults_dir / "runtime.json")

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

    @staticmethod
    def _reject_removed_runtime_key(key: str, *configs: dict[str, Any]) -> None:
        for config in configs:
            if key in config:
                raise ValueError(f"runtime.json must not define top-level {key!r}; assign Skills through AgentConfig.")

    def _expand_env_vars(self, obj: Any) -> Any:
        """Recursively expand ${VAR} and ~ in string values."""
        if isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._expand_env_vars(v) for v in obj]
        if isinstance(obj, str):
            return remap_default_home_string(obj)
        return obj

    def _remove_none_values(self, obj: Any) -> Any:
        """Recursively remove None values to allow Pydantic defaults."""
        if isinstance(obj, dict):
            return {k: self._remove_none_values(v) for k, v in obj.items() if v is not None}
        if isinstance(obj, list):
            return [self._remove_none_values(v) for v in obj if v is not None]
        return obj


def load_config(cli_overrides: dict[str, Any] | None = None) -> LeonSettings:
    """Convenience function to load runtime configuration."""
    return AgentLoader().load(cli_overrides=cli_overrides)
