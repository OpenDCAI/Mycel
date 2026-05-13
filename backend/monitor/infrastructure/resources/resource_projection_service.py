from __future__ import annotations

from typing import Any

from backend.monitor.infrastructure.resources.resource_overview_cache import (
    get_resource_overview_snapshot,
    refresh_resource_overview_sync,
)
from backend.sandboxes.resources.user_projection import list_user_resource_providers as build_user_resource_providers


def list_user_resource_providers(app: Any, user_id: str) -> dict[str, Any]:
    return build_user_resource_providers(app, user_id)


__all__ = [
    "get_resource_overview_snapshot",
    "list_user_resource_providers",
    "refresh_resource_overview_sync",
]
