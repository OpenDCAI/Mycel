from __future__ import annotations

from typing import Any

from backend.sandboxes.provider_factory import build_provider_from_config_name
from sandbox.resource_snapshot import probe_and_upsert_for_instance
from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo
from storage.runtime import upsert_resource_snapshot_for_sandbox


def _resolve_sandbox_provider(
    sandbox_id: str,
    *,
    make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
    build_provider_from_config_name_fn=build_provider_from_config_name,
) -> tuple[Any, str]:
    sandbox_key = str(sandbox_id or "").strip()
    if not sandbox_key:
        raise KeyError("Sandbox not found: ")

    repo = make_sandbox_monitor_repo_fn()
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

    provider = build_provider_from_config_name_fn(provider_name)
    if provider is None:
        raise RuntimeError(f"Could not initialize provider: {provider_name}")
    return provider, instance_id


def browse_sandbox(
    sandbox_id: str,
    path: str,
    *,
    make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
    build_provider_from_config_name_fn=build_provider_from_config_name,
) -> dict[str, Any]:
    from pathlib import PurePosixPath

    provider, instance_id = _resolve_sandbox_provider(
        sandbox_id,
        make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo_fn,
        build_provider_from_config_name_fn=build_provider_from_config_name_fn,
    )

    try:
        entries = provider.list_dir(instance_id, path)
    except Exception as exc:
        raise RuntimeError(f"Failed to list directory: {exc}") from exc

    norm_path = path or "/"
    items = []
    for entry in entries:
        name = str(entry.get("name") or "").strip()
        if not name or name.startswith("."):
            continue
        is_dir = entry.get("type") == "directory"
        child_path = f"{norm_path.rstrip('/')}/{name}"
        items.append({"name": name, "path": child_path, "is_dir": is_dir})

    items.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
    parent = str(PurePosixPath(norm_path).parent)
    parent_path = parent if parent != norm_path else None
    return {"current_path": norm_path, "parent_path": parent_path, "items": items}


_READ_MAX_BYTES = 100 * 1024


def read_sandbox(
    sandbox_id: str,
    path: str,
    *,
    make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
    build_provider_from_config_name_fn=build_provider_from_config_name,
) -> dict[str, Any]:
    provider, instance_id = _resolve_sandbox_provider(
        sandbox_id,
        make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo_fn,
        build_provider_from_config_name_fn=build_provider_from_config_name_fn,
    )

    try:
        content = provider.read_file(instance_id, path)
    except Exception as exc:
        raise RuntimeError(f"Failed to read file: {exc}") from exc

    truncated = False
    if len(content.encode()) > _READ_MAX_BYTES:
        content = content.encode()[:_READ_MAX_BYTES].decode(errors="replace")
        truncated = True

    return {"path": path, "content": content, "truncated": truncated}


def refresh_resource_snapshots(
    *,
    make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
    build_provider_from_config_name_fn=build_provider_from_config_name,
    probe_and_upsert_for_instance_fn=probe_and_upsert_for_instance,
    upsert_resource_snapshot_for_sandbox_fn=upsert_resource_snapshot_for_sandbox,
) -> dict[str, Any]:
    repo = make_sandbox_monitor_repo_fn()
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
        sandbox_id = item["sandbox_id"]
        if not sandbox_id:
            raise RuntimeError("Probe target missing sandbox_id")
        provider_key = item["provider_name"]
        instance_id = item["instance_id"]
        status = item["observed_state"]
        if status == "paused":
            continue
        probe_mode = "running_runtime" if status in ("running", "detached") else "non_running_sdk"
        if probe_mode == "running_runtime":
            running_targets += 1
        else:
            non_running_targets += 1

        provider = provider_cache.get(provider_key)
        if provider is None:
            provider = build_provider_from_config_name_fn(provider_key)
            provider_cache[provider_key] = provider
        if provider is None:
            upsert_resource_snapshot_for_sandbox_fn(
                sandbox_id=sandbox_id,
                provider_name=provider_key,
                observed_state=status,
                probe_mode=probe_mode,
                probe_error=f"provider init failed: {provider_key}",
            )
            errors += 1
            continue

        result = probe_and_upsert_for_instance_fn(
            sandbox_id=sandbox_id,
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
