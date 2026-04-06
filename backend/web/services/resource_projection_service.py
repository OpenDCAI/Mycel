"""User-visible resource projection service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.web.core.config import SANDBOXES_DIR
from backend.web.services import resource_service, sandbox_service
from sandbox.provider import RESOURCE_CAPABILITY_KEYS
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
    return {key: False for key in RESOURCE_CAPABILITY_KEYS}


def _build_provider_card(config_name: str, leases: list[dict[str, Any]]) -> dict[str, Any]:
    provider_name = resource_service.resolve_provider_name(config_name, sandboxes_dir=SANDBOXES_DIR)
    catalog = resource_service._CATALOG.get(provider_name)
    provider_type = resource_service._resolve_provider_type(provider_name, config_name, sandboxes_dir=SANDBOXES_DIR)
    capabilities, capability_error = resource_service._resolve_instance_capabilities(config_name)
    if capability_error:
        capabilities = _empty_capabilities()

    sessions: list[dict[str, Any]] = []
    running_count = 0
    for lease in leases:
        thread_id = str((lease.get("thread_ids") or [None])[0] or "")
        owner = (lease.get("agents") or [{}])[0]
        status = map_lease_to_session_status(lease.get("observed_state"), lease.get("desired_state"))
        if status == "running":
            running_count += 1
        sessions.append(
            {
                "id": f"{lease['lease_id']}:{thread_id}",
                "leaseId": lease["lease_id"],
                "threadId": thread_id,
                "memberId": str(owner.get("member_id") or ""),
                "memberName": str(owner.get("member_name") or "未绑定Agent"),
                "avatarUrl": owner.get("avatar_url"),
                "status": status,
                "startedAt": "",
                "metrics": None,
            }
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

    return {
        "id": config_name,
        "name": config_name,
        "description": catalog.description if catalog is not None else config_name,
        "vendor": catalog.vendor if catalog is not None else None,
        "type": provider_type,
        "status": "active" if running_count > 0 else "ready",
        "unavailableReason": capability_error,
        "error": ({"code": "PROVIDER_UNAVAILABLE", "message": capability_error} if capability_error else None),
        "capabilities": capabilities,
        "telemetry": telemetry,
        "cardCpu": dict(telemetry["cpu"]),
        "consoleUrl": resource_service._resolve_console_url(provider_name, config_name, sandboxes_dir=SANDBOXES_DIR),
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
