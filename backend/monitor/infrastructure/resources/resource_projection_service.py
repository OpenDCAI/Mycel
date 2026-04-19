"""Monitor-local access to product resource projections."""

from __future__ import annotations

from typing import Any

from backend.web.services import resource_projection_service
from backend.web.services.resource_cache import get_resource_overview_snapshot, refresh_resource_overview_sync


def list_user_resource_providers(app: Any, user_id: str) -> dict[str, Any]:
    return resource_projection_service.list_user_resource_providers(app, user_id)


__all__ = [
    "get_resource_overview_snapshot",
    "list_user_resource_providers",
    "refresh_resource_overview_sync",
]
