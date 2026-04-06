"""Lease resource probing helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sandbox.provider import SandboxProvider
from storage.runtime import build_resource_snapshot_repo


def ensure_resource_snapshot_table() -> None:
    """Noop — Supabase tables managed via migrations."""


def upsert_lease_resource_snapshot(**kwargs) -> None:  # type: ignore[no-untyped-def]
    repo = build_resource_snapshot_repo()
    try:
        repo.upsert_lease_resource_snapshot(**kwargs)
    finally:
        repo.close()


def list_snapshots_by_lease_ids(lease_ids: list[str], **kwargs) -> dict:  # type: ignore[no-untyped-def,type-arg]
    repo = build_resource_snapshot_repo()
    try:
        return repo.list_snapshots_by_lease_ids(lease_ids)
    finally:
        repo.close()


__all__ = [
    "ensure_resource_snapshot_table",
    "upsert_lease_resource_snapshot",
    "list_snapshots_by_lease_ids",
    "probe_and_upsert_for_instance",
]


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _metric_float(metrics: Any, field: str) -> float | None:
    try:
        return _as_float(getattr(metrics, field))
    except Exception:
        return None


def probe_and_upsert_for_instance(
    *,
    lease_id: str,
    provider_name: str,
    observed_state: str,
    probe_mode: str,
    provider: SandboxProvider,
    instance_id: str,
    repo: Any | None = None,
    db_path: Path | None = None,  # deprecated, ignored
) -> dict[str, Any]:
    """Probe provider metrics and persist to storage."""
    metrics = None
    cpu_used = None
    cpu_limit = None
    memory_used_mb = None
    memory_total_mb = None
    disk_used_gb = None
    disk_total_gb = None
    network_rx_kbps = None
    network_tx_kbps = None
    probe_error: str | None = None
    try:
        metrics = provider.get_metrics(instance_id)
    except Exception as exc:
        probe_error = str(exc)

    # @@@metrics-type-guard - Provider SDK/mocks may return non-numeric placeholders; persist only numeric metrics.
    if metrics is not None:
        cpu_used = _metric_float(metrics, "cpu_percent")
        cpu_limit = None
        memory_used_mb = _metric_float(metrics, "memory_used_mb")
        memory_total_mb = _metric_float(metrics, "memory_total_mb")
        disk_used_gb = _metric_float(metrics, "disk_used_gb")
        disk_total_gb = _metric_float(metrics, "disk_total_gb")
        network_rx_kbps = _metric_float(metrics, "network_rx_kbps")
        network_tx_kbps = _metric_float(metrics, "network_tx_kbps")

    if (
        cpu_used is None
        and memory_used_mb is None
        and memory_total_mb is None
        and disk_used_gb is None
        and disk_total_gb is None
        and network_rx_kbps is None
        and network_tx_kbps is None
    ) and probe_error is None:
        probe_error = "metrics unavailable"

    upsert = repo.upsert_lease_resource_snapshot if repo is not None else upsert_lease_resource_snapshot
    upsert(
        lease_id=lease_id,
        provider_name=provider_name,
        observed_state=observed_state,
        probe_mode=probe_mode,
        cpu_used=cpu_used,
        cpu_limit=cpu_limit,
        memory_used_mb=memory_used_mb,
        memory_total_mb=memory_total_mb,
        disk_used_gb=disk_used_gb,
        disk_total_gb=disk_total_gb,
        network_rx_kbps=network_rx_kbps,
        network_tx_kbps=network_tx_kbps,
        probe_error=probe_error,
    )
    return {"ok": probe_error is None, "error": probe_error}
