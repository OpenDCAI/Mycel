"""Supabase resource snapshot repo."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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
    client: Any = None,
) -> None:
    if client is None:
        raise RuntimeError("upsert_lease_resource_snapshot requires a client")
    now = _now_iso()
    client.table("lease_resource_snapshots").upsert(
        {
            "lease_id": lease_id,
            "provider_name": provider_name,
            "observed_state": observed_state,
            "probe_mode": probe_mode,
            "cpu_used": cpu_used,
            "cpu_limit": cpu_limit,
            "memory_used_mb": memory_used_mb,
            "memory_total_mb": memory_total_mb,
            "disk_used_gb": disk_used_gb,
            "disk_total_gb": disk_total_gb,
            "network_rx_kbps": network_rx_kbps,
            "network_tx_kbps": network_tx_kbps,
            "probe_error": probe_error,
            "collected_at": now,
            "updated_at": now,
        }
    ).execute()


def list_snapshots_by_lease_ids(
    lease_ids: list[str],
    client: Any = None,
) -> dict[str, dict[str, Any]]:
    if client is None:
        raise RuntimeError("list_snapshots_by_lease_ids requires a client")
    if not lease_ids:
        return {}
    unique_ids = sorted({lid for lid in lease_ids if lid})
    if not unique_ids:
        return {}
    from storage.providers.supabase import _query as q

    rows = q.rows_in_chunks(
        lambda: client.table("lease_resource_snapshots").select("*"),
        "lease_id",
        unique_ids,
        "resource_snapshot",
        "list_by_ids",
    )
    return {str(r["lease_id"]): dict(r) for r in rows}


class SupabaseResourceSnapshotRepo:
    def __init__(self, client: Any) -> None:
        self._client = client

    def close(self) -> None:
        return None

    def upsert_resource_snapshot_for_sandbox(
        self,
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
        if not sandbox_id:
            raise RuntimeError("sandbox-shaped snapshot repo write requires sandbox_id")
        upsert_lease_resource_snapshot(
            lease_id=legacy_lease_id,
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
            client=self._client,
        )

    def upsert_lease_resource_snapshot(
        self,
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
        upsert_lease_resource_snapshot(
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
            client=self._client,
        )

    def list_snapshots_by_sandbox_ids(self, sessions: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
        lease_ids: list[str] = []
        sandbox_by_lease: dict[str, str] = {}
        for session in sessions:
            sandbox_id = str(session.get("sandbox_id") or "").strip()
            lease_id = str(session.get("lease_id") or "").strip()
            if not sandbox_id or not lease_id or lease_id in sandbox_by_lease:
                continue
            sandbox_by_lease[lease_id] = sandbox_id
            lease_ids.append(lease_id)

        snapshot_by_lease = list_snapshots_by_lease_ids(lease_ids, client=self._client)
        snapshot_by_sandbox: dict[str, dict[str, Any]] = {}
        for lease_id, snapshot in snapshot_by_lease.items():
            sandbox_id = sandbox_by_lease.get(lease_id)
            if sandbox_id:
                snapshot_by_sandbox[sandbox_id] = snapshot
        return snapshot_by_sandbox

    def list_snapshots_by_lease_ids(self, lease_ids: list[str]) -> dict[str, dict[str, Any]]:
        return list_snapshots_by_lease_ids(lease_ids, client=self._client)
