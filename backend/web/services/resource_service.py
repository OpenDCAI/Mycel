"""Resource probe and sandbox filesystem service."""

from __future__ import annotations

from typing import Any

from backend import resource_provider_contracts as _resource_provider_contracts
from backend.resource_io import browse_sandbox as run_browse_sandbox
from backend.resource_io import read_sandbox as run_read_sandbox
from backend.resource_io import refresh_resource_snapshots as run_refresh_resource_snapshots
from backend.sandbox_provider_factory import build_provider_from_config_name
from sandbox.resource_snapshot import probe_and_upsert_for_instance
from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo
from storage.runtime import upsert_resource_snapshot_for_sandbox

get_provider_display_contract = _resource_provider_contracts.get_provider_display_contract
get_provider_capability_contract = _resource_provider_contracts.get_provider_capability_contract
build_provider_availability_payload = _resource_provider_contracts.build_provider_availability_payload
build_resource_row_payload = _resource_provider_contracts.build_resource_row_payload


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
