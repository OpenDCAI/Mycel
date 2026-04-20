"""Shared sandbox provider availability helpers."""

from __future__ import annotations

from typing import Any

from backend.sandbox_inventory import init_providers_and_managers
from backend.sandbox_paths import SANDBOXES_DIR
from sandbox.config import SandboxConfig


def available_sandbox_types(
    *,
    sandboxes_dir=SANDBOXES_DIR,
    init_providers_and_managers_fn=init_providers_and_managers,
    sandbox_config_cls=SandboxConfig,
) -> list[dict[str, Any]]:
    from backend import sandbox_inventory

    return sandbox_inventory.available_sandbox_types(
        sandboxes_dir=sandboxes_dir,
        init_providers_and_managers_fn=init_providers_and_managers_fn,
        sandbox_config_cls=sandbox_config_cls,
    )
