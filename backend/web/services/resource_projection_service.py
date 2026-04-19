"""Compatibility shell for shared resource projection helpers."""

from backend.resource_projection import (
    _load_visible_resource_runtime,
    _project_user_visible_resource_rows,
    _resource_display_status,
    _resource_row_identity,
    _resource_running_identity,
    list_resource_providers,
    list_user_resource_providers,
    visible_resource_row_stats,
)

__all__ = [
    "_load_visible_resource_runtime",
    "_project_user_visible_resource_rows",
    "_resource_display_status",
    "_resource_row_identity",
    "_resource_running_identity",
    "list_resource_providers",
    "list_user_resource_providers",
    "visible_resource_row_stats",
]
