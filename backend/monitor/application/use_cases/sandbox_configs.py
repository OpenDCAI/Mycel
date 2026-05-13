from __future__ import annotations

from typing import Any

from backend.monitor.infrastructure.config import app_config_service
from backend.monitor.infrastructure.providers import sandbox_config_provider_service


def get_monitor_sandbox_configs() -> dict[str, Any]:
    providers = sandbox_config_provider_service.available_sandbox_types()
    return {
        "source": "runtime_sandbox_inventory",
        "default_local_cwd": str(app_config_service.local_workspace_root()),
        "count": len(providers),
        "providers": providers,
    }
