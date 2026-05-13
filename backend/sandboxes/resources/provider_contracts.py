from __future__ import annotations

from typing import Any

from backend.sandboxes.paths import SANDBOXES_DIR
from backend.sandboxes.resources.common import CATALOG as _CATALOG
from backend.sandboxes.resources.common import CatalogEntry as _CatalogEntry
from backend.sandboxes.resources.common import resolve_console_url as _resolve_console_url
from backend.sandboxes.resources.common import resolve_instance_capabilities as _resolve_instance_capabilities
from backend.sandboxes.resources.common import resolve_provider_name
from backend.sandboxes.resources.common import resolve_provider_type as _resolve_provider_type
from backend.sandboxes.resources.common import to_resource_status as _to_resource_status


def get_provider_display_contract(config_name: str) -> dict[str, Any]:
    provider_name = resolve_provider_name(config_name, sandboxes_dir=SANDBOXES_DIR)
    catalog = _CATALOG.get(provider_name) or _CatalogEntry(vendor=None, description=provider_name, provider_type="cloud")
    return {
        "provider_name": provider_name,
        "description": catalog.description,
        "vendor": catalog.vendor,
        "type": _resolve_provider_type(provider_name),
        "console_url": _resolve_console_url(provider_name, config_name, sandboxes_dir=SANDBOXES_DIR),
    }


def get_provider_capability_contract(config_name: str) -> tuple[dict[str, bool], str | None]:
    return _resolve_instance_capabilities(config_name)


def build_provider_availability_payload(*, available: bool, running_count: int, unavailable_reason: str | None) -> dict[str, Any]:
    return {
        "status": _to_resource_status(available, running_count),
        "unavailableReason": unavailable_reason,
        "error": ({"code": "PROVIDER_UNAVAILABLE", "message": unavailable_reason} if unavailable_reason else None),
    }


def build_resource_row_payload(
    *,
    resource_identity: str,
    sandbox_id: str | None = None,
    thread_id: str,
    runtime_id: str | None,
    owner: dict[str, Any],
    status: str,
    started_at: str,
    metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = {
        "id": resource_identity,
        "threadId": thread_id,
        "agentUserId": owner.get("agent_user_id"),
        "agentName": str(owner.get("agent_name") or "未绑定Agent"),
        "avatarUrl": owner.get("avatar_url"),
        "status": status,
        "startedAt": started_at,
        "metrics": metrics,
    }
    if sandbox_id:
        payload["sandboxId"] = sandbox_id
    if runtime_id:
        payload["runtimeId"] = runtime_id
    return payload
