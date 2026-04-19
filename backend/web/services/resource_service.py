"""Resource probe and sandbox filesystem service."""

from __future__ import annotations

from typing import Any

from backend.resource_common import CATALOG as _CATALOG
from backend.resource_common import CatalogEntry as _CatalogEntry
from backend.resource_common import resolve_console_url as _resolve_console_url
from backend.resource_common import resolve_instance_capabilities as _resolve_instance_capabilities
from backend.resource_common import resolve_provider_name
from backend.resource_common import resolve_provider_type as _resolve_provider_type
from backend.resource_common import to_resource_status as _to_resource_status
from backend.resource_io import browse_sandbox as run_browse_sandbox
from backend.resource_io import read_sandbox as run_read_sandbox
from backend.resource_io import refresh_resource_snapshots as run_refresh_resource_snapshots
from backend.sandbox_provider_factory import build_provider_from_config_name
from backend.web.core.config import SANDBOXES_DIR
from sandbox.resource_snapshot import probe_and_upsert_for_instance
from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo
from storage.runtime import upsert_resource_snapshot_for_sandbox


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


def _resolve_sandbox_provider(sandbox_id: str) -> tuple[Any, str]:
    sandbox_key = str(sandbox_id or "").strip()
    if not sandbox_key:
        raise KeyError("Sandbox not found: ")

    repo = make_sandbox_monitor_repo()
    try:
        instance_id = repo.query_sandbox_instance_id(sandbox_key)
        provider_name = ""
        for row in repo.query_sandboxes():
            if str(row.get("sandbox_id") or "").strip() == sandbox_key:
                provider_name = str(row.get("provider_name") or "").strip()
                break
    finally:
        repo.close()

    if not provider_name:
        raise KeyError(f"Sandbox not found: {sandbox_key}")
    if not instance_id:
        raise RuntimeError("No active instance for this sandbox — sandbox may be destroyed or paused")

    provider = build_provider_from_config_name(provider_name)
    if provider is None:
        raise RuntimeError(f"Could not initialize provider: {provider_name}")
    return provider, instance_id


def browse_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    return run_browse_sandbox(
        sandbox_id,
        path,
        make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
        build_provider_from_config_name_fn=build_provider_from_config_name,
    )


_READ_MAX_BYTES = 100 * 1024


def read_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    return run_read_sandbox(
        sandbox_id,
        path,
        make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
        build_provider_from_config_name_fn=build_provider_from_config_name,
    )


def refresh_resource_snapshots() -> dict[str, Any]:
    return run_refresh_resource_snapshots(
        make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
        build_provider_from_config_name_fn=build_provider_from_config_name,
        probe_and_upsert_for_instance_fn=probe_and_upsert_for_instance,
        upsert_resource_snapshot_for_sandbox_fn=upsert_resource_snapshot_for_sandbox,
    )
