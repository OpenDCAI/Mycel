"""Compatibility shell for thread runtime launch config helpers."""

from typing import Any

from backend.thread_runtime import launch_config as _owner
from backend.web.services import sandbox_service
from backend.web.services.library_service import list_library

normalize_launch_config_payload = _owner.normalize_launch_config_payload
build_new_launch_config = _owner.build_new_launch_config


def resolve_default_config(app: Any, owner_user_id: str, agent_user_id: str) -> dict[str, Any]:
    _owner.available_sandbox_types = sandbox_service.available_sandbox_types
    _owner.list_library = list_library
    return _owner.resolve_default_config(app, owner_user_id, agent_user_id)
