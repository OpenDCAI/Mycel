"""User-visible resource projection over shared resource facts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.web.core.config import SANDBOXES_DIR
from backend.web.services import resource_service, sandbox_service
from backend.web.services.resource_common import CATALOG as _CATALOG
from backend.web.services.resource_common import CatalogEntry as _CatalogEntry
from backend.web.services.resource_common import aggregate_provider_telemetry as _aggregate_provider_telemetry
from backend.web.services.resource_common import metric as _metric
from backend.web.services.resource_common import resolve_card_cpu_metric as _resolve_card_cpu_metric
from backend.web.services.resource_common import resolve_console_url as _resolve_console_url
from backend.web.services.resource_common import resolve_instance_capabilities as _resolve_instance_capabilities
from backend.web.services.resource_common import resolve_provider_name
from backend.web.services.resource_common import resolve_provider_type as _resolve_provider_type
from backend.web.services.resource_common import thread_owners as _thread_owners
from backend.web.services.resource_common import to_resource_metrics as _to_resource_metrics
from backend.web.services.resource_common import to_resource_status as _to_resource_status
from backend.web.services.sandbox_service import available_sandbox_types
from sandbox.providers.local import LocalSessionProvider
from storage.models import map_sandbox_state_to_display_status
from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo
from storage.runtime import list_resource_snapshots_by_sandbox


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _empty_metric(unit: str) -> dict[str, Any]:
    return {
        "used": None,
        "limit": None,
        "unit": unit,
        "source": "unknown",
        "freshness": "stale",
    }


def _build_provider_card(config_name: str, sandboxes: list[dict[str, Any]]) -> dict[str, Any]:
    display = resource_service.get_provider_display_contract(config_name)
    capabilities, capability_error = resource_service.get_provider_capability_contract(config_name)
    provider_type = str(display["type"])

    resource_rows: list[dict[str, Any]] = []
    running_count = 0
    for sandbox in sandboxes:
        thread_id = str((sandbox.get("thread_ids") or [None])[0] or "")
        owner = (sandbox.get("agents") or [{}])[0]
        status = map_sandbox_state_to_display_status(sandbox.get("observed_state"), sandbox.get("desired_state"))
        if status == "running":
            running_count += 1
        sandbox_id = str(sandbox.get("sandbox_id") or "").strip() or None
        secondary_identity = str(sandbox.get("runtime_session_id") or "sandbox").strip()
        resource_identity = f"{sandbox_id}:{thread_id}" if sandbox_id and thread_id else f"{secondary_identity}:{thread_id}"
        resource_rows.append(
            resource_service.build_resource_row_payload(
                resource_identity=resource_identity,
                sandbox_id=sandbox_id,
                thread_id=thread_id,
                runtime_session_id=sandbox.get("runtime_session_id"),
                owner=owner,
                status=status,
                started_at=str(sandbox.get("created_at") or ""),
                metrics=None,
            )
        )

    telemetry = {
        "running": {
            "used": running_count,
            "limit": None,
            "unit": "sandbox",
            "source": "derived",
            "freshness": "live",
        },
        "cpu": _empty_metric("%"),
        "memory": _empty_metric("GB"),
        "disk": _empty_metric("GB"),
    }
    availability = resource_service.build_provider_availability_payload(
        available=capability_error is None,
        running_count=running_count,
        unavailable_reason=capability_error,
    )

    return {
        "id": config_name,
        "name": config_name,
        "description": display["description"],
        "vendor": display["vendor"],
        "type": provider_type,
        **availability,
        "capabilities": capabilities,
        "telemetry": telemetry,
        "cardCpu": dict(telemetry["cpu"]),
        "consoleUrl": display["console_url"],
        "sessions": resource_rows,
    }


def _query_runtime_session_ids(repo: Any, sandbox_ids: list[str]) -> dict[str, str | None]:
    ordered_ids = []
    seen: set[str] = set()
    for sandbox_id in sandbox_ids:
        normalized = str(sandbox_id or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered_ids.append(normalized)
    if not ordered_ids:
        return {}

    return repo.query_sandbox_instance_ids(ordered_ids)


def _load_runtime_session_ids(sandbox_ids: list[str]) -> dict[str, str | None]:
    repo = make_sandbox_monitor_repo()
    try:
        return _query_runtime_session_ids(repo, sandbox_ids)
    finally:
        repo.close()


def _load_visible_resource_runtime() -> tuple[
    list[dict[str, Any]],
    dict[str, str | None],
    dict[str, dict[str, Any]],
]:
    repo = make_sandbox_monitor_repo()
    try:
        resource_rows = _project_user_visible_resource_rows(repo, repo.query_resource_sessions())
        runtime_session_ids = _query_runtime_session_ids(
            repo, [str(resource_row.get("sandbox_id") or "") for resource_row in resource_rows]
        )
    finally:
        repo.close()

    snapshot_by_sandbox = list_resource_snapshots_by_sandbox(resource_rows)
    return resource_rows, runtime_session_ids, snapshot_by_sandbox


def _backfill_runtime_session_ids(sandboxes: list[dict[str, Any]]) -> None:
    pending_sandboxes = [sandbox for sandbox in sandboxes if not str(sandbox.get("runtime_session_id") or "").strip()]
    if not pending_sandboxes:
        return

    runtime_session_ids = _load_runtime_session_ids([str(sandbox.get("sandbox_id") or "") for sandbox in pending_sandboxes])
    for sandbox in pending_sandboxes:
        sandbox_id = str(sandbox.get("sandbox_id") or "").strip()
        runtime_session_id = runtime_session_ids.get(sandbox_id)
        if runtime_session_id:
            sandbox["runtime_session_id"] = runtime_session_id


def list_user_resource_providers(app: Any, owner_user_id: str) -> dict[str, Any]:
    thread_repo = getattr(app.state, "thread_repo", None)
    user_repo = getattr(app.state, "user_repo", None)
    if thread_repo is None or user_repo is None:
        raise RuntimeError("thread_repo and user_repo are required")

    sandboxes = sandbox_service.list_user_sandboxes(
        owner_user_id,
        thread_repo=thread_repo,
        user_repo=user_repo,
    )
    _backfill_runtime_session_ids(sandboxes)

    sandboxes_by_provider: dict[str, list[dict[str, Any]]] = {}
    for sandbox in sandboxes:
        config_name = str(sandbox.get("provider_name") or "local")
        sandboxes_by_provider.setdefault(config_name, []).append(sandbox)

    providers = [
        _build_provider_card(config_name, provider_sandboxes) for config_name, provider_sandboxes in sorted(sandboxes_by_provider.items())
    ]

    return {
        "summary": {
            "snapshot_at": _now_iso(),
            "total_providers": len(providers),
            "active_providers": len([item for item in providers if item["status"] == "active"]),
            "unavailable_providers": len([item for item in providers if item["status"] == "unavailable"]),
            "running_sessions": sum(int(item["telemetry"]["running"]["used"] or 0) for item in providers),
            "scope": "user",
            "sandbox_count": len(sandboxes),
        },
        "providers": providers,
    }


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
    runtime_session_id: str | None,
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
    if observed == "detached" and desired == "running" and not runtime_session_id and resource_metrics is None:
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

        # @@@resource-visible-parent-projection - visible resource cards are now
        # sandbox-first. If the raw monitor row lands on a hidden/subagent
        # thread, only sandbox truth can authorize a visible-parent projection.
        # Rows without sandbox truth are no longer eligible for
        # visible-parent projection on the user-facing resource surface.
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
    resource_rows, runtime_session_ids, snapshot_by_sandbox = _load_visible_resource_runtime()

    grouped: dict[str, list[dict[str, Any]]] = {}
    for resource_row in resource_rows:
        provider_instance = str(resource_row.get("provider") or "local")
        grouped.setdefault(provider_instance, []).append(resource_row)

    owners = _thread_owners([str(resource_row["thread_id"]) for resource_row in resource_rows if resource_row.get("thread_id")])

    providers: list[dict[str, Any]] = []
    for item in available_sandbox_types():
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
            runtime_session_id = runtime_session_ids.get(str(resource_row.get("sandbox_id") or "").strip())
            resource_metrics = _to_resource_metrics(snapshot_by_sandbox.get(sandbox_id))
            normalized = _resource_display_status(
                observed_state=observed_state,
                desired_state=desired_state,
                runtime_session_id=runtime_session_id,
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
                resource_service.build_resource_row_payload(
                    resource_identity=resource_identity,
                    sandbox_id=str(resource_row.get("sandbox_id") or "").strip() or None,
                    thread_id=thread_id,
                    runtime_session_id=runtime_session_id,
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
                "sessions": normalized_resource_rows,
            }
        )

    summary = {
        "snapshot_at": _now_iso(),
        "total_providers": len(providers),
        "active_providers": len([provider for provider in providers if provider.get("status") == "active"]),
        "unavailable_providers": len([provider for provider in providers if provider.get("status") == "unavailable"]),
        "running_sessions": sum(int((provider.get("telemetry") or {}).get("running", {}).get("used") or 0) for provider in providers),
    }
    return {"summary": summary, "providers": providers}


def visible_resource_row_stats() -> dict[str, dict[str, int]]:
    resource_rows, runtime_session_ids, snapshot_by_sandbox = _load_visible_resource_runtime()
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
        runtime_session_id = runtime_session_ids.get(sandbox_id)
        normalized = _resource_display_status(
            observed_state=resource_row.get("observed_state"),
            desired_state=resource_row.get("desired_state"),
            runtime_session_id=runtime_session_id,
            resource_metrics=_to_resource_metrics(snapshot_by_sandbox.get(sandbox_id)),
        )
        running_identity = _resource_running_identity(resource_row)
        scoped_running_identity = (provider_instance, running_identity)
        if normalized == "running" and running_identity and scoped_running_identity not in seen_running_sandboxes:
            seen_running_sandboxes.add(scoped_running_identity)
            provider_stats["running"] += 1

    return stats
