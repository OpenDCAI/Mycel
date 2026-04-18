"""Provider/runtime read and cleanup boundary for Monitor."""

from __future__ import annotations

from typing import Any

from backend.web.services import monitor_operation_service, sandbox_service
from backend.web.services.resource_cache import get_resource_overview_snapshot


def list_monitor_provider_orphan_runtimes() -> dict[str, Any]:
    _, managers = sandbox_service.init_providers_and_managers()
    runtimes = []
    for item in sandbox_service.load_provider_orphan_runtimes(managers):
        runtimes.append(
            {
                "runtime_id": str(item.get("session_id") or ""),
                "provider": str(item.get("provider") or ""),
                "status": str(item.get("status") or "unknown"),
                "source": "provider_orphan",
            }
        )
    return {"count": len(runtimes), "runtimes": runtimes}


def get_monitor_provider_detail(provider_id: str) -> dict[str, Any]:
    snapshot = get_resource_overview_snapshot()
    providers = snapshot.get("providers") or []
    provider = next((item for item in providers if str(item.get("id") or "") == provider_id), None)
    if provider is None:
        raise KeyError(f"Provider not found: {provider_id}")

    resource_rows = provider.get("sessions") or []
    return {
        "provider": provider,
        "sandbox_ids": _resource_row_values(resource_rows, "sandboxId"),
        "runtime_session_ids": _resource_row_values(resource_rows, "runtimeSessionId"),
    }


def _resource_row_values(resource_rows: list[dict[str, Any]], key: str) -> list[str]:
    return sorted({str(item.get(key) or "").strip() for item in resource_rows if str(item.get(key) or "").strip()})


def get_monitor_runtime_detail(runtime_session_id: str) -> dict[str, Any]:
    snapshot = get_resource_overview_snapshot()
    for provider in snapshot.get("providers") or []:
        for resource_row in provider.get("sessions") or []:
            current = str(resource_row.get("runtimeSessionId") or "").strip()
            if current != runtime_session_id:
                continue
            return {
                "provider": {
                    "id": provider.get("id"),
                    "name": provider.get("name"),
                    "status": provider.get("status"),
                    "consoleUrl": provider.get("consoleUrl"),
                },
                "runtime": resource_row,
                "sandbox_id": resource_row.get("sandboxId"),
                "thread_id": resource_row.get("threadId"),
            }
    raise KeyError(f"Runtime not found: {runtime_session_id}")


def request_monitor_provider_orphan_runtime_cleanup(provider_name: str, runtime_id: str) -> dict[str, Any]:
    provider = str(provider_name or "").strip()
    runtime = str(runtime_id or "").strip()
    for item in list_monitor_provider_orphan_runtimes().get("runtimes", []):
        if str(item.get("provider") or "").strip() == provider and str(item.get("runtime_id") or "").strip() == runtime:
            runtime_truth = item
            return monitor_operation_service.request_provider_orphan_runtime_cleanup(provider, runtime, runtime_truth)
    raise KeyError(f"Provider orphan runtime not found: {provider}:{runtime}")
