"""Shared user-scoped resource projection helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import backend.resource_provider_boundary as resource_provider_boundary
from backend.monitor.infrastructure.read_models import resource_runtime_service
from storage.models import map_sandbox_state_to_display_status


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
    display = resource_provider_boundary.get_provider_display_contract(config_name)
    capabilities, capability_error = resource_provider_boundary.get_provider_capability_contract(config_name)
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
        secondary_identity = str(sandbox.get("runtime_id") or "sandbox").strip()
        resource_identity = f"{sandbox_id}:{thread_id}" if sandbox_id and thread_id else f"{secondary_identity}:{thread_id}"
        resource_rows.append(
            resource_provider_boundary.build_resource_row_payload(
                resource_identity=resource_identity,
                sandbox_id=sandbox_id,
                thread_id=thread_id,
                runtime_id=sandbox.get("runtime_id"),
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
    availability = resource_provider_boundary.build_provider_availability_payload(
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
        "resource_rows": resource_rows,
    }


def _backfill_runtime_ids(sandboxes: list[dict[str, Any]]) -> None:
    pending_sandboxes = [sandbox for sandbox in sandboxes if not str(sandbox.get("runtime_id") or "").strip()]
    if not pending_sandboxes:
        return

    runtime_ids = resource_runtime_service.load_runtime_ids([str(sandbox.get("sandbox_id") or "") for sandbox in pending_sandboxes])
    for sandbox in pending_sandboxes:
        sandbox_id = str(sandbox.get("sandbox_id") or "").strip()
        runtime_id = runtime_ids.get(sandbox_id)
        if runtime_id:
            sandbox["runtime_id"] = runtime_id


def list_user_resource_providers(app: Any, owner_user_id: str) -> dict[str, Any]:
    sandboxes = resource_provider_boundary.load_user_sandboxes(app, owner_user_id)
    _backfill_runtime_ids(sandboxes)

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
            "running_resource_rows": sum(int(item["telemetry"]["running"]["used"] or 0) for item in providers),
            "scope": "user",
            "sandbox_count": len(sandboxes),
        },
        "providers": providers,
    }
