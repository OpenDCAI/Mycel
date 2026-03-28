"""Three-tier observation configuration loader.

Follows the same pattern as ConfigLoader / ModelsLoader:
system defaults → user (~/.leon/observation.json) → project (.leon/observation.json) → CLI overrides
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from config.observation_schema import ObservationConfig
from config.user_paths import remap_legacy_user_home_string, user_home_read_candidates


class ObservationLoader:
    """Three-tier observation.json loader."""

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self._system_dir = Path(__file__).parent / "defaults"

    def load(self, cli_overrides: dict[str, Any] | None = None) -> ObservationConfig:
        """Load and merge observation config from all tiers."""
        system = self._load_json(self._system_dir / "observation.json")
        user = self._load_user()
        project = self._load_project()

        merged = self._deep_merge(system, user, project)

        # CLI overrides: explicit None for "active" means disable, so apply directly
        if cli_overrides:
            for key, value in cli_overrides.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = self._deep_merge(merged[key], value)
                else:
                    merged[key] = value

        merged = self._expand_env_vars(merged)

        return ObservationConfig(**merged)

    def _load_project(self) -> dict[str, Any]:
        if not self.workspace_root:
            return {}
        return self._load_json(self.workspace_root / ".leon" / "observation.json")

    def _load_user(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for path in user_home_read_candidates("observation.json"):
            merged = self._deep_merge(merged, self._load_json(path))
        return merged

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
        """Deep merge multiple dicts. Later dicts override earlier ones."""
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

    def _expand_env_vars(self, obj: Any) -> Any:
        """Recursively expand ${VAR} and ~ in string values."""
        if isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._expand_env_vars(v) for v in obj]
        if isinstance(obj, str):
            return remap_legacy_user_home_string(obj)
        return obj
