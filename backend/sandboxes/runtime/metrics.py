"""Shared sandbox runtime metrics helpers."""

from __future__ import annotations

from typing import Any

from backend.sandboxes.inventory import init_providers_and_managers


def _exact_rows_for_provider_runtime(
    runtimes: list[dict[str, Any]],
    *,
    runtime_id: str,
    provider_name: str,
) -> list[dict[str, Any]]:
    return [row for row in runtimes if row.get("provider") == provider_name and str(row.get("session_id") or "") == runtime_id]


def get_runtime_metrics(
    runtime_id: str,
    provider_hint: str | None = None,
    *,
    init_providers_and_managers_fn=init_providers_and_managers,
    load_all_sandbox_runtimes_fn,
    find_runtime_and_manager_fn,
) -> dict[str, Any]:
    _, managers = init_providers_and_managers_fn()
    runtimes = load_all_sandbox_runtimes_fn(managers)
    try:
        runtime, manager = find_runtime_and_manager_fn(runtimes, managers, runtime_id, provider_name=provider_hint)
    except RuntimeError as exc:
        if "Ambiguous runtime id" not in str(exc) or not provider_hint:
            raise
        # @@@provider-hinted-runtime-collapse - metrics reads should treat duplicate
        # rows for the same provider/session as one runtime when the caller already
        # supplied the provider hint; the ambiguity is cross-thread residue, not a
        # reason to fail the high-level metrics surface.
        exact = _exact_rows_for_provider_runtime(
            runtimes,
            runtime_id=runtime_id,
            provider_name=provider_hint,
        )
        if not exact:
            raise
        runtime = exact[0]
        manager = managers.get(provider_hint)
    if not runtime:
        raise RuntimeError(f"Runtime not found: {runtime_id}")
    if manager is None:
        raise RuntimeError(f"Provider manager unavailable: {runtime.get('provider')}")

    target_runtime_id = str(runtime.get("instance_id") or runtime.get("session_id") or runtime_id)
    metrics = manager.provider.get_metrics(target_runtime_id)
    if metrics is None:
        return {"session_id": target_runtime_id, "provider": runtime.get("provider"), "metrics": None}
    return {
        "session_id": target_runtime_id,
        "provider": runtime.get("provider"),
        "metrics": {
            "cpu_percent": metrics.cpu_percent,
            "memory_used_mb": metrics.memory_used_mb,
            "memory_total_mb": metrics.memory_total_mb,
            "disk_used_gb": metrics.disk_used_gb,
            "disk_total_gb": metrics.disk_total_gb,
            "network_rx_kbps": metrics.network_rx_kbps,
            "network_tx_kbps": metrics.network_tx_kbps,
        },
    }
