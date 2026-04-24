from __future__ import annotations

from typing import Any


def build_provider_from_config_name(name: str, *, sandboxes_dir=None) -> Any | None:
    from backend.sandboxes.inventory import init_providers_and_managers

    providers, _ = init_providers_and_managers()
    if name in providers:
        return providers[name]
    return None
