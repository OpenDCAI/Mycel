"""Resource probe and sandbox filesystem service."""

from __future__ import annotations

from typing import Any

from backend.web.core.config import SANDBOXES_DIR
from backend.web.core.storage_factory import make_sandbox_monitor_repo, upsert_resource_snapshot
from backend.web.services import resource_projection_service
from backend.web.services.resource_common import (
    CATALOG as _CATALOG,
)
from backend.web.services.resource_common import (
    resolve_console_url as _resolve_console_url,
)
from backend.web.services.resource_common import (
    resolve_instance_capabilities as _resolve_instance_capabilities,
)
from backend.web.services.resource_common import (
    resolve_provider_name,
)
from backend.web.services.resource_common import (
    resolve_provider_type as _resolve_provider_type,
)
from backend.web.services.sandbox_service import build_provider_from_config_name
from sandbox.resource_snapshot import (
    ensure_resource_snapshot_table,
    probe_and_upsert_for_instance,
)

# ---------------------------------------------------------------------------
# Public API: sandbox filesystem browse
# ---------------------------------------------------------------------------


def list_resource_providers() -> dict[str, Any]:
    return resource_projection_service.list_resource_providers()


def visible_resource_session_stats() -> dict[str, dict[str, int]]:
    return resource_projection_service.visible_resource_session_stats()


def get_provider_display_contract(config_name: str) -> dict[str, Any]:
    provider_name = resolve_provider_name(config_name, sandboxes_dir=SANDBOXES_DIR)
    catalog = _CATALOG.get(provider_name)
    description = catalog.description if catalog else provider_name
    vendor = catalog.vendor if catalog else None
    provider_type = _resolve_provider_type(provider_name, config_name, sandboxes_dir=SANDBOXES_DIR)
    console_url = _resolve_console_url(provider_name, config_name, sandboxes_dir=SANDBOXES_DIR)
    return {
        "provider_name": provider_name,
        "description": description,
        "vendor": vendor,
        "type": provider_type,
        "console_url": console_url,
    }


def get_provider_capability_contract(config_name: str) -> tuple[dict[str, bool], str | None]:
    return _resolve_instance_capabilities(config_name)


def sandbox_browse(lease_id: str, path: str) -> dict[str, Any]:
    """Browse the filesystem of a sandbox lease via its provider."""
    from pathlib import PurePosixPath

    repo = make_sandbox_monitor_repo()
    try:
        lease = repo.query_lease(lease_id)
        instance_id = repo.query_lease_instance_id(lease_id)
    finally:
        repo.close()

    if not lease:
        raise KeyError(f"Lease not found: {lease_id}")

    provider_name = str(lease.get("provider_name") or "").strip()
    if not provider_name:
        raise RuntimeError("Lease has no provider")

    if not instance_id:
        raise RuntimeError("No active instance for this lease — sandbox may be destroyed or paused")

    provider = build_provider_from_config_name(provider_name)
    if provider is None:
        raise RuntimeError(f"Could not initialize provider: {provider_name}")

    try:
        entries = provider.list_dir(instance_id, path)
    except Exception as exc:
        raise RuntimeError(f"Failed to list directory: {exc}") from exc

    norm_path = path if path else "/"

    items = []
    for entry in entries:
        name = str(entry.get("name") or "").strip()
        if not name or name.startswith("."):
            continue
        is_dir = entry.get("type") == "directory"
        child_path = f"{norm_path.rstrip('/')}/{name}"
        items.append({"name": name, "path": child_path, "is_dir": is_dir})

    # Dirs first, then files, each alphabetically
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

    parent = str(PurePosixPath(norm_path).parent)
    parent_path = parent if parent != norm_path else None

    return {"current_path": norm_path, "parent_path": parent_path, "items": items}


_READ_MAX_BYTES = 100 * 1024  # 100 KB


def sandbox_read(lease_id: str, path: str) -> dict[str, Any]:
    """Read a file from a sandbox lease via its provider."""
    repo = make_sandbox_monitor_repo()
    try:
        lease = repo.query_lease(lease_id)
        instance_id = repo.query_lease_instance_id(lease_id)
    finally:
        repo.close()

    if not lease:
        raise KeyError(f"Lease not found: {lease_id}")

    provider_name = str(lease.get("provider_name") or "").strip()
    if not provider_name:
        raise RuntimeError("Lease has no provider")

    if not instance_id:
        raise RuntimeError("No active instance for this lease — sandbox may be destroyed or paused")

    provider = build_provider_from_config_name(provider_name)
    if provider is None:
        raise RuntimeError(f"Could not initialize provider: {provider_name}")

    try:
        content = provider.read_file(instance_id, path)
    except Exception as exc:
        raise RuntimeError(f"Failed to read file: {exc}") from exc

    truncated = False
    if len(content.encode()) > _READ_MAX_BYTES:
        content = content.encode()[:_READ_MAX_BYTES].decode(errors="replace")
        truncated = True

    return {"path": path, "content": content, "truncated": truncated}


# ---------------------------------------------------------------------------
# Public API: resource probe
# ---------------------------------------------------------------------------


def refresh_resource_snapshots() -> dict[str, Any]:
    """Probe active lease instances and upsert resource snapshots."""
    ensure_resource_snapshot_table()
    repo = make_sandbox_monitor_repo()
    try:
        probe_targets = repo.list_probe_targets()
    finally:
        repo.close()

    provider_cache: dict[str, Any] = {}
    probed = 0
    errors = 0
    running_targets = 0
    non_running_targets = 0

    for item in probe_targets:
        lease_id = item["lease_id"]
        provider_key = item["provider_name"]
        instance_id = item["instance_id"]
        status = item["observed_state"]
        # detached means running (not connected to terminal)
        probe_mode = "running_runtime" if status in ("running", "detached") else "non_running_sdk"
        if probe_mode == "running_runtime":
            running_targets += 1
        else:
            non_running_targets += 1

        provider = provider_cache.get(provider_key)
        if provider is None:
            provider = build_provider_from_config_name(provider_key)
            provider_cache[provider_key] = provider
        if provider is None:
            upsert_resource_snapshot(
                lease_id=lease_id,
                provider_name=provider_key,
                observed_state=status,
                probe_mode=probe_mode,
                probe_error=f"provider init failed: {provider_key}",
            )
            errors += 1
            continue

        result = probe_and_upsert_for_instance(
            lease_id=lease_id,
            provider_name=provider_key,
            observed_state=status,
            probe_mode=probe_mode,
            provider=provider,
            instance_id=instance_id,
        )
        probed += 1
        if not result["ok"]:
            errors += 1

    return {
        "probed": probed,
        "errors": errors,
        "running_targets": running_targets,
        "non_running_targets": non_running_targets,
    }
