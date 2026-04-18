"""Sandbox provider inventory boundary for Monitor."""

from __future__ import annotations

from typing import Any

from backend.web.core import config as web_config
from backend.web.services import monitor_sandbox_config_provider_service


def get_monitor_sandbox_configs() -> dict[str, Any]:
    providers = monitor_sandbox_config_provider_service.available_sandbox_types()
    return {
        "source": "runtime_sandbox_inventory",
        "default_local_cwd": str(web_config.LOCAL_WORKSPACE_ROOT),
        "count": len(providers),
        "providers": providers,
    }
