"""Lease resource probing helpers."""

from __future__ import annotations

from typing import Any

from sandbox.provider import SandboxProvider
from storage.runtime import build_resource_snapshot_repo


def upsert_resource_snapshot_for_sandbox(
    *,
    sandbox_id: str,
    legacy_lease_id: str,
    provider_name: str,
    observed_state: str,
    probe_mode: str,
    cpu_used: float | None = None,
    cpu_limit: float | None = None,
    memory_used_mb: float | None = None,
    memory_total_mb: float | None = None,
    disk_used_gb: float | None = None,
    disk_total_gb: float | None = None,
    network_rx_kbps: float | None = None,
    network_tx_kbps: float | None = None,
    probe_error: str | None = None,
) -> None:
    repo = build_resource_snapshot_repo()
    try:
        repo.upsert_resource_snapshot_for_sandbox(
            sandbox_id=sandbox_id,
            legacy_lease_id=legacy_lease_id,
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
    finally:
        repo.close()


def upsert_lease_resource_snapshot(
    *,
    lease_id: str,
    provider_name: str,
    observed_state: str,
    probe_mode: str,
    cpu_used: float | None = None,
    cpu_limit: float | None = None,
    memory_used_mb: float | None = None,
    memory_total_mb: float | None = None,
    disk_used_gb: float | None = None,
    disk_total_gb: float | None = None,
    network_rx_kbps: float | None = None,
    network_tx_kbps: float | None = None,
    probe_error: str | None = None,
) -> None:
    repo = build_resource_snapshot_repo()
    try:
        repo.upsert_lease_resource_snapshot(
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
    finally:
        repo.close()


__all__ = [
    "upsert_resource_snapshot_for_sandbox",
    "upsert_lease_resource_snapshot",
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
    sandbox_id: str | None = None,
    lease_id: str,
    provider_name: str,
    observed_state: str,
    probe_mode: str,
    provider: SandboxProvider,
    instance_id: str,
    repo: Any | None = None,
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

    try:
        # @@@snapshot-write-nonblocking - runtime startup truth belongs to lease/session creation;
        # snapshot persistence is auxiliary monitor data and must report write failure
        # without turning local sandbox bringup into a Supabase-config contract.
        if repo is not None and hasattr(repo, "upsert_resource_snapshot_for_sandbox"):
            if not sandbox_id:
                raise RuntimeError("sandbox-shaped snapshot repo requires sandbox_id")
            repo.upsert_resource_snapshot_for_sandbox(
                sandbox_id=sandbox_id,
                legacy_lease_id=lease_id,
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
        else:
            # @@@snapshot-runtime-active-path - mainline runtime/helper flow should prefer
            # sandbox-shaped write entry when sandbox_id is already present; the lease-shaped
            # helper remains only as compatibility residue for callers that still lack sandbox truth.
            if sandbox_id:
                upsert_resource_snapshot_for_sandbox(
                    sandbox_id=sandbox_id,
                    legacy_lease_id=lease_id,
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
            else:
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
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": probe_error is None, "error": probe_error}
