from __future__ import annotations

from typing import Any

from backend.sandboxes.paths import SANDBOXES_DIR
from sandbox.config import SandboxConfig


def available_sandbox_types(
    *,
    sandboxes_dir=SANDBOXES_DIR,
    build_providers_fn=None,
    sandbox_config_cls=SandboxConfig,
) -> list[dict[str, Any]]:
    from backend.sandboxes import inventory as sandbox_inventory

    return sandbox_inventory.available_sandbox_types(
        sandboxes_dir=sandboxes_dir,
        build_providers_fn=build_providers_fn,
        sandbox_config_cls=sandbox_config_cls,
    )
