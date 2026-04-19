"""Neutral sandbox provider factory helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.sandbox_paths import SANDBOXES_DIR


def build_provider_from_config_name(name: str, *, sandboxes_dir: Path | None = None) -> Any | None:
    """Build one provider instance from sandbox config name."""
    from backend.sandbox_inventory import init_providers_and_managers

    providers, _ = init_providers_and_managers()
    if name in providers:
        return providers[name]
    _sandboxes_dir = sandboxes_dir or SANDBOXES_DIR
    config_path = _sandboxes_dir / f"{name}.json"
    if not config_path.exists():
        return None
    return None
