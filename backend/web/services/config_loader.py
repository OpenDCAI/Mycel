"""Centralized sandbox configuration loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SandboxConfigLoader:
    """Loads sandbox provider configurations from JSON files."""

    def __init__(self, sandboxes_dir: Path):
        self.sandboxes_dir = sandboxes_dir

    def load(self, config_name: str) -> dict[str, Any]:
        """Load configuration payload for a sandbox config."""
        if config_name == "local":
            return {"provider": "local"}
        config_path = self.sandboxes_dir / f"{config_name}.json"
        payload = json.loads(config_path.read_text())
        if not isinstance(payload, dict):
            raise RuntimeError(f"Sandbox config is not a JSON object: {config_path}")
        return payload

    def get_provider_name(self, config_name: str) -> str:
        """Extract provider name from config."""
        payload = self.load(config_name)
        provider = str(payload.get("provider") or "").strip()
        if not provider:
            raise RuntimeError(f"Sandbox config missing provider: {config_name}")
        return provider
