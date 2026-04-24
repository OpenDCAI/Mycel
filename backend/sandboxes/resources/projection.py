from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import backend.sandboxes.resources.provider_boundary as resource_provider_boundary
from backend.sandboxes.paths import SANDBOXES_DIR
from backend.sandboxes.resources import runtime_service as resource_runtime_service
from backend.sandboxes.resources.common import CATALOG as _CATALOG
from backend.sandboxes.resources.common import CatalogEntry as _CatalogEntry
from backend.sandboxes.resources.common import aggregate_provider_telemetry as _aggregate_provider_telemetry
from backend.sandboxes.resources.common import metric as _metric
from backend.sandboxes.resources.common import resolve_card_cpu_metric as _resolve_card_cpu_metric
from backend.sandboxes.resources.common import resolve_console_url as _resolve_console_url
from backend.sandboxes.resources.common import resolve_instance_capabilities as _resolve_instance_capabilities
from backend.sandboxes.resources.common import resolve_provider_name
from backend.sandboxes.resources.common import resolve_provider_type as _resolve_provider_type
from backend.sandboxes.resources.common import thread_owners as _thread_owners
from backend.sandboxes.resources.common import to_resource_metrics as _to_resource_metrics
from backend.sandboxes.resources.common import to_resource_status as _to_resource_status
from backend.sandboxes.resources.user_projection import list_user_resource_providers as _list_user_resource_providers
from sandbox.providers.local import LocalSessionProvider
from storage.models import map_sandbox_state_to_display_status


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_visible_resource_runtime() -> tuple[
    list[dict[str, Any]],
    dict[str, str | None],
    dict[str, dict[str, Any]],
]:
    return resource_runtime_service.load_visible_resource_runtime(_project_user_visible_resource_rows)


def list_user_resource_providers(app: Any, owner_user_id: str) -> dict[str, Any]:
    return _list_user_resource_providers(app, owner_user_id)


def _is_resource_visible_thread(thread_id: str | None) -> bool:
    raw = str(thread_id or "").strip()
    return not raw.startswith("subagent-")


def _resource_row_identity(resource_row: dict[str, Any]) -> str:
    sandbox_id = str(resource_row.get("sandbox_id") or "")
    thread_id = str(resource_row.get("thread_id") or "")
    # @@@resource-row-identity - resource rows are sandbox-first on the user-visible surface.
    # Provider-native runtime ids are only an unbound-runtime secondary identity; bound rows use
    # sandbox/thread identity on the user-visible Resources surface.
    if sandbox_id and thread_id:
        return f"{sandbox_id}:{thread_id}"
    provider_runtime_identity = str(resource_row.get("session_id") or "")
    if provider_runtime_identity:
        return provider_runtime_identity
    return thread_id or "unbound"


def _resource_running_identity(resource_row: dict[str, Any]) -> str:
    sandbox_id = str(resource_row.get("sandbox_id") or "").strip()
    return sandbox_id


def _resource_display_status(
    *,
    observed_state: str | None,
    desired_state: str | None,
    runtime_id: str | None,
    resource_metrics: dict[str, Any] | None,
) -> str:
    status = map_sandbox_state_to_display_status(observed_state, desired_state)
    observed = str(observed_state or "").strip().lower()
    desired = str(desired_state or "").strip().lower()
    if status != "running":
        return status
    # @@@resource-detached-residue - monitor/resources should not inflate running counts with
    # detached sandbox rows that have neither a bound runtime nor any live/quota snapshot. Those rows
    # are residue on this operator surface, even if the product-facing desired state still says running.
    if observed == "detached" and desired == "running" and not runtime_id and resource_metrics is None:
        return "stopped"
    return status


def _project_user_visible_resource_rows(repo: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project raw monitor rows into the user-visible resource surface."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        sandbox_id = str(row.get("sandbox_id") or "").strip()
        if not sandbox_id:
            continue
        grouped.setdefault(sandbox_id, []).append(dict(row))

    projected: list[dict[str, Any]] = []
    for sandbox_id, group in grouped.items():
        visible_rows = [row for row in group if _is_resource_visible_thread(row.get("thread_id"))]
        if visible_rows:
            projected.extend(visible_rows)
            continue

        # @@@resource-visible-parent-projection - hidden/subagent rows need sandbox truth for visible-parent projection.
        thread_rows = repo.query_sandbox_threads(sandbox_id)
        preferred_thread_id = next(
            (str(item.get("thread_id") or "").strip() for item in thread_rows if _is_resource_visible_thread(item.get("thread_id"))),
            "",
        )
        if not preferred_thread_id:
            continue

        base = dict(group[0])
        base["thread_id"] = preferred_thread_id
        base["session_id"] = None
        projected.append(base)

    return projected


def list_resource_providers() -> dict[str, Any]:
    resource_rows, runtime_ids, snapshot_by_sandbox = _load_visible_resource_runtime()

    grouped: dict[str, list[dict[str, Any]]] = {}
    for resource_row in resource_rows:
        provider_instance = str(resource_row.get("provider") or "local")
        grouped.setdefault(provider_instance, []).append(resource_row)

    owners = _thread_owners([str(resource_row["thread_id"]) for resource_row in resource_rows if resource_row.get("thread_id")])

    providers: list[dict[str, Any]] = []
    for item in resource_provider_boundary.available_sandbox_types():
        config_name = str(item["name"])
        available = bool(item.get("available"))
        provider_name = resolve_provider_name(config_name, sandboxes_dir=SANDBOXES_DIR)
        catalog = _CATALOG.get(provider_name) or _CatalogEntry(vendor=None, description=provider_name, provider_type="cloud")
        capabilities, capability_error = _resolve_instance_capabilities(config_name)
        effective_available = available and capability_error is None
        unavailable_reason: str | None = None
        if not effective_available:
            unavailable_reason = str(item.get("reason") or capability_error or "provider unavailable")

        provider_resource_rows = grouped.get(config_name, [])
        normalized_resource_rows: list[dict[str, Any]] = []
        seen_resource_ids: set[str] = set()
        running_count = 0
        seen_running_sandboxes: set[str] = set()
        for resource_row in provider_resource_rows:
            observed_state = resource_row.get("observed_state")
            desired_state = resource_row.get("desired_state")
            thread_id = str(resource_row.get("thread_id") or "")
            sandbox_id = str(resource_row.get("sandbox_id") or "").strip()
            runtime_id = runtime_ids.get(str(resource_row.get("sandbox_id") or "").strip())
            resource_metrics = _to_resource_metrics(snapshot_by_sandbox.get(sandbox_id))
            normalized = _resource_display_status(
                observed_state=observed_state,
                desired_state=desired_state,
                runtime_id=runtime_id,
                resource_metrics=resource_metrics,
            )
            running_identity = _resource_running_identity(resource_row)
            if normalized == "running" and running_identity and running_identity not in seen_running_sandboxes:
                running_count += 1
                seen_running_sandboxes.add(running_identity)
            owner = owners.get(thread_id, {"agent_name": "未绑定Agent", "avatar_url": None})
            resource_identity = _resource_row_identity(resource_row)
            if resource_identity in seen_resource_ids:
                continue
            seen_resource_ids.add(resource_identity)
            normalized_resource_rows.append(
                resource_provider_boundary.build_resource_row_payload(
                    resource_identity=resource_identity,
                    sandbox_id=str(resource_row.get("sandbox_id") or "").strip() or None,
                    thread_id=thread_id,
                    runtime_id=runtime_id,
                    owner=owner,
                    status=normalized,
                    started_at=str(resource_row.get("created_at") or ""),
                    metrics=resource_metrics,
                )
            )

        provider_type = _resolve_provider_type(provider_name)
        telemetry = _aggregate_provider_telemetry(
            provider_resource_rows=provider_resource_rows,
            running_count=running_count,
            snapshot_by_sandbox={
                str(resource_row.get("sandbox_id") or "").strip(): snapshot_by_sandbox[str(resource_row.get("sandbox_id") or "").strip()]
                for resource_row in provider_resource_rows
                if str(resource_row.get("sandbox_id") or "").strip() in snapshot_by_sandbox
            },
        )
        if config_name == "local" and effective_available and capabilities.get("metrics"):
            host_metrics = LocalSessionProvider().get_metrics("host")
            if host_metrics is not None:
                telemetry = {
                    "running": telemetry["running"],
                    "cpu": _metric(host_metrics.cpu_percent, None, "%", "direct", "live"),
                    "memory": _metric(
                        host_metrics.memory_used_mb / 1024.0 if host_metrics.memory_used_mb is not None else None,
                        host_metrics.memory_total_mb / 1024.0 if host_metrics.memory_total_mb is not None else None,
                        "GB",
                        "direct",
                        "live",
                    ),
                    "disk": _metric(host_metrics.disk_used_gb, host_metrics.disk_total_gb, "GB", "direct", "live"),
                }
        providers.append(
            {
                "id": config_name,
                "name": config_name,
                "description": catalog.description,
                "vendor": catalog.vendor,
                "type": provider_type,
                "status": _to_resource_status(effective_available, running_count),
                "unavailableReason": unavailable_reason,
                "error": ({"code": "PROVIDER_UNAVAILABLE", "message": unavailable_reason} if unavailable_reason else None),
                "capabilities": capabilities,
                "telemetry": telemetry,
                "cardCpu": _resolve_card_cpu_metric(provider_type, telemetry),
                "consoleUrl": _resolve_console_url(provider_name, config_name, sandboxes_dir=SANDBOXES_DIR),
                "resource_rows": normalized_resource_rows,
            }
        )

    summary = {
        "snapshot_at": _now_iso(),
        "total_providers": len(providers),
        "active_providers": len([provider for provider in providers if provider.get("status") == "active"]),
        "unavailable_providers": len([provider for provider in providers if provider.get("status") == "unavailable"]),
        "running_resource_rows": sum(int((provider.get("telemetry") or {}).get("running", {}).get("used") or 0) for provider in providers),
    }
    return {"summary": summary, "providers": providers}


def visible_resource_row_stats() -> dict[str, dict[str, int]]:
    resource_rows, runtime_ids, snapshot_by_sandbox = _load_visible_resource_runtime()
    stats: dict[str, dict[str, int]] = {}
    seen_resource_ids: set[str] = set()
    seen_running_sandboxes: set[tuple[str, str]] = set()
    for resource_row in resource_rows:
        provider_instance = str(resource_row.get("provider") or "local")
        provider_stats = stats.setdefault(provider_instance, {"resource_rows": 0, "running": 0})
        resource_identity = _resource_row_identity(resource_row)
        if resource_identity not in seen_resource_ids:
            seen_resource_ids.add(resource_identity)
            provider_stats["resource_rows"] += 1

        sandbox_id = str(resource_row.get("sandbox_id") or "").strip()
        runtime_id = runtime_ids.get(sandbox_id)
        normalized = _resource_display_status(
            observed_state=resource_row.get("observed_state"),
            desired_state=resource_row.get("desired_state"),
            runtime_id=runtime_id,
            resource_metrics=_to_resource_metrics(snapshot_by_sandbox.get(sandbox_id)),
        )
        running_identity = _resource_running_identity(resource_row)
        scoped_running_identity = (provider_instance, running_identity)
        if normalized == "running" and running_identity and scoped_running_identity not in seen_running_sandboxes:
            seen_running_sandboxes.add(scoped_running_identity)
            provider_stats["running"] += 1

    return stats
