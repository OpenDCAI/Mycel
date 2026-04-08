"""User-visible resource projection over shared resource facts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.web.core.config import SANDBOXES_DIR
from backend.web.core.storage_factory import list_resource_snapshots, make_sandbox_monitor_repo
from backend.web.services import resource_service, sandbox_service
from backend.web.services.resource_common import CATALOG as _CATALOG
from backend.web.services.resource_common import CatalogEntry as _CatalogEntry
from backend.web.services.resource_common import aggregate_provider_telemetry as _aggregate_provider_telemetry
from backend.web.services.resource_common import empty_capabilities, resolve_provider_name
from backend.web.services.resource_common import metric as _metric
from backend.web.services.resource_common import resolve_card_cpu_metric as _resolve_card_cpu_metric
from backend.web.services.resource_common import resolve_console_url as _resolve_console_url
from backend.web.services.resource_common import resolve_instance_capabilities as _resolve_instance_capabilities
from backend.web.services.resource_common import resolve_provider_type as _resolve_provider_type
from backend.web.services.resource_common import thread_owners as _thread_owners
from backend.web.services.resource_common import to_resource_status as _to_resource_status
from backend.web.services.resource_common import to_session_metrics as _to_session_metrics
from backend.web.services.sandbox_service import available_sandbox_types
from sandbox.provider import RESOURCE_CAPABILITY_KEYS
from sandbox.providers.local import LocalSessionProvider
from storage.models import map_lease_to_session_status


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


def _empty_capabilities() -> dict[str, bool]:
    return empty_capabilities() if callable(empty_capabilities) else {key: False for key in RESOURCE_CAPABILITY_KEYS}


def _build_provider_card(config_name: str, leases: list[dict[str, Any]]) -> dict[str, Any]:
    display = resource_service.get_provider_display_contract(config_name)
    capabilities, capability_error = resource_service.get_provider_capability_contract(config_name)
    provider_type = str(display["type"])

    sessions: list[dict[str, Any]] = []
    running_count = 0
    for lease in leases:
        thread_id = str((lease.get("thread_ids") or [None])[0] or "")
        owner = (lease.get("agents") or [{}])[0]
        status = map_lease_to_session_status(lease.get("observed_state"), lease.get("desired_state"))
        if status == "running":
            running_count += 1
        sessions.append(
            resource_service.build_resource_session_payload(
                session_identity=f"{lease['lease_id']}:{thread_id}",
                lease_id=str(lease["lease_id"]),
                thread_id=thread_id,
                owner=owner,
                status=status,
                started_at=str(lease.get("created_at") or ""),
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
        "sessions": sessions,
    }


def list_user_resource_providers(app: Any, owner_user_id: str) -> dict[str, Any]:
    thread_repo = getattr(app.state, "thread_repo", None)
    member_repo = getattr(app.state, "member_repo", None)
    if thread_repo is None or member_repo is None:
        raise RuntimeError("thread_repo and member_repo are required")

    leases = sandbox_service.list_user_leases(
        owner_user_id,
        thread_repo=thread_repo,
        member_repo=member_repo,
    )

    leases_by_provider: dict[str, list[dict[str, Any]]] = {}
    for lease in leases:
        config_name = str(lease.get("provider_name") or "local")
        leases_by_provider.setdefault(config_name, []).append(lease)

    providers = [_build_provider_card(config_name, provider_leases) for config_name, provider_leases in sorted(leases_by_provider.items())]

    return {
        "summary": {
            "snapshot_at": _now_iso(),
            "total_providers": len(providers),
            "active_providers": len([item for item in providers if item["status"] == "active"]),
            "unavailable_providers": len([item for item in providers if item["status"] == "unavailable"]),
            "running_sessions": sum(int(item["telemetry"]["running"]["used"] or 0) for item in providers),
            "scope": "user",
            "lease_count": len(leases),
        },
        "providers": providers,
    }


def _is_resource_visible_thread(thread_id: str | None) -> bool:
    raw = str(thread_id or "").strip()
    if raw.startswith("subagent-"):
        return False
    return True


def _resource_session_identity(session: dict[str, Any]) -> str:
    lease_id = str(session.get("lease_id") or "")
    thread_id = str(session.get("thread_id") or "")
    if lease_id and thread_id:
        # @@@resource-session-contract - resource cards are lease/thread scoped, not chat-session scoped.
        # Terminal fallback rows can carry distinct session ids for the same visible lease+thread binding.
        return f"{lease_id}:{thread_id}"
    session_id = str(session.get("session_id") or "")
    if session_id:
        return session_id
    return f"{lease_id}:{thread_id or 'unbound'}"


def _project_user_visible_resource_sessions(repo: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project raw monitor rows into the user-visible resource surface."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        lease_id = str(row.get("lease_id") or "")
        grouped.setdefault(lease_id, []).append(dict(row))

    projected: list[dict[str, Any]] = []
    for lease_id, group in grouped.items():
        visible_rows = [row for row in group if _is_resource_visible_thread(row.get("thread_id"))]
        if visible_rows:
            projected.extend(visible_rows)
            continue

        if not lease_id:
            continue

        try:
            thread_rows = repo.query_lease_threads(lease_id)
        except Exception:
            thread_rows = []

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
    repo = make_sandbox_monitor_repo()
    try:
        raw_sessions = repo.list_sessions_with_leases()
        sessions = _project_user_visible_resource_sessions(repo, raw_sessions)
    finally:
        repo.close()

    grouped: dict[str, list[dict[str, Any]]] = {}
    for session in sessions:
        provider_instance = str(session.get("provider") or "local")
        grouped.setdefault(provider_instance, []).append(session)

    owners = _thread_owners([str(session["thread_id"]) for session in sessions if session.get("thread_id")])
    snapshot_by_lease = list_resource_snapshots([str(session.get("lease_id") or "") for session in sessions])

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

        provider_sessions = grouped.get(config_name, [])
        normalized_sessions: list[dict[str, Any]] = []
        seen_session_ids: set[str] = set()
        running_count = 0
        seen_running_leases: set[str] = set()
        for session in provider_sessions:
            observed_state = session.get("observed_state")
            desired_state = session.get("desired_state")
            normalized = map_lease_to_session_status(observed_state, desired_state)
            thread_id = str(session.get("thread_id") or "")
            lease_id = str(session.get("lease_id") or "")
            if normalized == "running" and lease_id not in seen_running_leases:
                running_count += 1
                seen_running_leases.add(lease_id)
            session_metrics = _to_session_metrics(snapshot_by_lease.get(lease_id))
            owner = owners.get(thread_id, {"agent_name": "未绑定Agent", "avatar_url": None})
            session_identity = _resource_session_identity(session)
            if session_identity in seen_session_ids:
                continue
            seen_session_ids.add(session_identity)
            normalized_sessions.append(
                resource_service.build_resource_session_payload(
                    session_identity=session_identity,
                    lease_id=lease_id,
                    thread_id=thread_id,
                    owner=owner,
                    status=normalized,
                    started_at=str(session.get("created_at") or ""),
                    metrics=session_metrics,
                )
            )

        provider_type = _resolve_provider_type(provider_name, config_name, sandboxes_dir=SANDBOXES_DIR)
        telemetry = _aggregate_provider_telemetry(
            provider_sessions=provider_sessions,
            running_count=running_count,
            snapshot_by_lease=snapshot_by_lease,
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
                "sessions": normalized_sessions,
            }
        )

    summary = {
        "snapshot_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "total_providers": len(providers),
        "active_providers": len([provider for provider in providers if provider.get("status") == "active"]),
        "unavailable_providers": len([provider for provider in providers if provider.get("status") == "unavailable"]),
        "running_sessions": sum(int((provider.get("telemetry") or {}).get("running", {}).get("used") or 0) for provider in providers),
    }
    return {"summary": summary, "providers": providers}


def visible_resource_session_stats() -> dict[str, dict[str, int]]:
    repo = make_sandbox_monitor_repo()
    try:
        raw_sessions = repo.list_sessions_with_leases()
        sessions = _project_user_visible_resource_sessions(repo, raw_sessions)
    finally:
        repo.close()

    stats: dict[str, dict[str, int]] = {}
    seen_session_ids: set[str] = set()
    seen_running_leases: set[tuple[str, str]] = set()
    for session in sessions:
        provider_instance = str(session.get("provider") or "local")
        provider_stats = stats.setdefault(provider_instance, {"sessions": 0, "running": 0})
        session_identity = _resource_session_identity(session)
        if session_identity not in seen_session_ids:
            seen_session_ids.add(session_identity)
            provider_stats["sessions"] += 1

        lease_id = str(session.get("lease_id") or "")
        normalized = map_lease_to_session_status(session.get("observed_state"), session.get("desired_state"))
        running_identity = (provider_instance, lease_id)
        if normalized == "running" and lease_id and running_identity not in seen_running_leases:
            seen_running_leases.add(running_identity)
            provider_stats["running"] += 1

    return stats
