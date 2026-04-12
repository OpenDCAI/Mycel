"""Three-tier models.json loader.

Merge priority: system defaults → user (~/.leon/models.json) → project (.leon/models.json) → CLI overrides

Merge strategies:
- providers: deep merge (per-provider)
- mapping: deep merge (per-key)
- pool: last wins (no list merge)
- catalog / virtual_models: system-only, not overridden
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.models_schema import ModelsConfig
from config.user_paths import remap_legacy_user_home_string, user_home_read_candidates


class ModelsLoader:
    """Three-tier models.json loader."""

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self._system_dir = Path(__file__).parent / "defaults"

    def load(self, cli_overrides: dict[str, Any] | None = None) -> ModelsConfig:
        """Load and merge models config from all tiers."""
        system = self._load_json(self._system_dir / "models.json")
        user = self._load_user()
        project = self._load_project()

        # Merge: system → user → project
        merged = self._merge(system, user)
        merged = self._merge(merged, project)

        # CLI overrides
        if cli_overrides:
            merged = self._merge(merged, cli_overrides)

        # Expand env vars in string values
        merged = self._expand_env_vars(merged)

        # catalog and virtual_models come only from system
        merged["catalog"] = system.get("catalog", [])
        merged["virtual_models"] = system.get("virtual_models", [])

        return ModelsConfig(**merged)

    def load_with_user_config(
        self,
        user_config: dict[str, Any] | None,
        cli_overrides: dict[str, Any] | None = None,
    ) -> ModelsConfig:
        """Load system + explicit user config + project config.

        Web runtime supplies repo-backed user config explicitly. It must not
        read the local operator's home directory as a silent user-settings layer.
        """
        system = self._load_json(self._system_dir / "models.json")
        merged = self._merge(system, user_config or {})
        merged = self._merge(merged, self._load_project())
        if cli_overrides:
            merged = self._merge(merged, cli_overrides)
        merged = self._expand_env_vars(merged)
        merged["catalog"] = system.get("catalog", [])
        merged["virtual_models"] = system.get("virtual_models", [])
        return ModelsConfig(**merged)

    def _load_project(self) -> dict[str, Any]:
        if not self.workspace_root:
            return {}
        return self._load_json(self.workspace_root / ".leon" / "models.json")

    def _load_user(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for path in user_home_read_candidates("models.json"):
            merged = self._merge(merged, self._load_json(path))
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

    def _merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Merge override into base with field-specific strategies."""
        if not override:
            return base.copy()

        result = base.copy()

        # active: last wins (only from CLI overrides, not persisted)
        if "active" in override:
            result["active"] = override["active"]

        # providers: deep merge per-provider
        if "providers" in override:
            base_providers = result.get("providers", {})
            for name, cfg in override["providers"].items():
                if name in base_providers and isinstance(base_providers[name], dict) and isinstance(cfg, dict):
                    merged = {**base_providers[name], **{k: v for k, v in cfg.items() if v is not None}}
                    base_providers[name] = merged
                else:
                    base_providers[name] = cfg
            result["providers"] = base_providers

        # mapping: deep merge per-key
        if "mapping" in override:
            base_mapping = result.get("mapping", {})
            for name, spec in override["mapping"].items():
                if name in base_mapping and isinstance(base_mapping[name], dict) and isinstance(spec, dict):
                    merged_spec = {**base_mapping[name], **{k: v for k, v in spec.items() if v is not None}}
                    # If model changed but provider not explicitly overridden, clear inherited provider
                    if "model" in spec and "provider" not in spec:
                        merged_spec.pop("provider", None)
                    base_mapping[name] = merged_spec
                else:
                    base_mapping[name] = spec
            result["mapping"] = base_mapping

        # pool: last wins
        if "pool" in override:
            result["pool"] = override["pool"]

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


def load_models(
    workspace_root: str | Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> ModelsConfig:
    """Convenience function to load models config."""
    return ModelsLoader(workspace_root=workspace_root).load(cli_overrides=cli_overrides)
