"""Supabase resource snapshot repo (module-level functions, mirrors SQLite interface)."""

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

    rows: list[dict[str, Any]] = []
    for chunk in q.value_chunks(unique_ids):
        rows.extend(
            q.rows(
                q.in_(
                    client.table("lease_resource_snapshots").select("*"),
                    "lease_id",
                    chunk,
                    "resource_snapshot",
                    "list_by_ids",
                ).execute(),
                "resource_snapshot",
                "list_by_ids",
            )
        )
    return {str(r["lease_id"]): dict(r) for r in rows}


class SupabaseResourceSnapshotRepo:
    def __init__(self, client: Any) -> None:
        self._client = client

    def close(self) -> None:
        return None

    def upsert_lease_resource_snapshot(self, **kwargs: Any) -> None:
        upsert_lease_resource_snapshot(**kwargs, client=self._client)

    def list_snapshots_by_lease_ids(self, lease_ids: list[str]) -> dict[str, dict[str, Any]]:
        return list_snapshots_by_lease_ids(lease_ids, client=self._client)
