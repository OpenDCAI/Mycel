"""Webhook endpoints for provider events."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.web.services.sandbox_service import init_providers_and_managers
from backend.web.utils.helpers import extract_webhook_instance_id
from sandbox.config import DEFAULT_DB_PATH as SANDBOX_DB_PATH
from sandbox.lease import LeaseStore
from sandbox.provider_events import ProviderEventStore

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/{provider_name}")
async def ingest_provider_webhook(provider_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Ingest provider webhook: persist provider event and converge lease observed state."""
    instance_id = extract_webhook_instance_id(payload)
    if not instance_id:
        raise HTTPException(400, "Webhook payload missing instance/session id")

    event_type = str(payload.get("event") or payload.get("type") or "unknown")
    store = LeaseStore(db_path=SANDBOX_DB_PATH)
    event_store = ProviderEventStore(db_path=SANDBOX_DB_PATH)
    lease = await asyncio.to_thread(store.find_by_instance, provider_name=provider_name, instance_id=instance_id)
    matched_lease_id = lease.lease_id if lease else None

    # @@@webhook-invalidation-only - Webhook is optimization only: persist event + mark lease stale.
    await asyncio.to_thread(
        event_store.record,
        provider_name=provider_name,
        instance_id=instance_id,
        event_type=event_type,
        payload=payload,
        matched_lease_id=matched_lease_id,
    )

    if not lease:
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
        lease.apply,
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
        "lease_id": lease.lease_id,
    }


@router.get("/events")
async def list_provider_events(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
    """List recent provider webhook events."""
    store = ProviderEventStore(db_path=SANDBOX_DB_PATH)
    items = await asyncio.to_thread(store.list_recent, limit)
    return {"items": items, "count": len(items)}
