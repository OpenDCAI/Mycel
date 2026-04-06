"""User-visible resource projection service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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
