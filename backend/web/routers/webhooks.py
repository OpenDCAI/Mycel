"""Webhook endpoints for provider events."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.web.services.sandbox_service import init_providers_and_managers
from backend.web.utils.helpers import _get_container, extract_webhook_instance_id
from sandbox.control_plane_repos import resolve_sandbox_db_path
from sandbox.lease import lease_from_row as lower_runtime_from_row
from storage.runtime import build_lease_repo as make_lower_runtime_repo

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _public_provider_event(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "matched_runtime_handle"}


@router.post("/{provider_name}")
async def ingest_provider_webhook(provider_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Ingest provider webhook and converge matched lower-runtime state."""
    instance_id = extract_webhook_instance_id(payload)
    if not instance_id:
        raise HTTPException(400, "Webhook payload missing instance/session id")

    event_type = str(payload.get("event") or payload.get("type") or "unknown")
    runtime_repo = make_lower_runtime_repo()
    event_repo = _get_container().provider_event_repo()
    try:
        runtime_row = await asyncio.to_thread(runtime_repo.find_by_instance, provider_name=provider_name, instance_id=instance_id)
        lower_runtime = lower_runtime_from_row(runtime_row, resolve_sandbox_db_path()) if runtime_row else None
        matched_runtime_handle = lower_runtime.lease_id if lower_runtime else None
        matched_sandbox_id = str((runtime_row or {}).get("sandbox_id") or "").strip() or None

        # @@@webhook-runtime-observation - Webhook is optimization only: persist event + observe lower-runtime state.
        await asyncio.to_thread(
            event_repo.record,
            provider_name=provider_name,
            instance_id=instance_id,
            event_type=event_type,
            payload=payload,
            matched_runtime_handle=matched_runtime_handle,
            matched_sandbox_id=matched_sandbox_id,
        )
    finally:
        runtime_repo.close()
        event_repo.close()

    if not lower_runtime:
        return {
            "ok": True,
            "provider": provider_name,
            "instance_id": instance_id,
            "event_type": event_type,
            "matched": False,
        }
    status_hint = str(payload.get("status") or payload.get("state") or payload.get("event") or "unknown").lower()
    if "pause" in status_hint:
        status_hint = "paused"
    elif "resume" in status_hint or "start" in status_hint or "running" in status_hint:
        status_hint = "running"
    elif "destroy" in status_hint or "delete" in status_hint or "stop" in status_hint:
        status_hint = "detached"
    else:
        status_hint = "unknown"

    _, managers = await asyncio.to_thread(init_providers_and_managers)
    manager = managers.get(provider_name)
    if not manager:
        raise HTTPException(503, f"Provider manager unavailable: {provider_name}")
    await asyncio.to_thread(
        lower_runtime.apply,
        manager.provider,
        event_type="observe.status",
        source="webhook",
        payload={"status": status_hint, "raw_event_type": event_type},
    )
    return {
        "ok": True,
        "provider": provider_name,
        "instance_id": instance_id,
        "event_type": event_type,
        "matched": True,
    }


@router.get("/events")
async def list_provider_events(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
    """List recent provider webhook events."""
    repo = _get_container().provider_event_repo()
    try:
        items = await asyncio.to_thread(repo.list_recent, limit)
    finally:
        repo.close()
    return {"items": [_public_provider_event(item) for item in items], "count": len(items)}
