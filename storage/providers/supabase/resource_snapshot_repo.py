"""Supabase resource snapshot repo."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "resource snapshot repo"
_SCHEMA = "container"
_TABLE = "resource_snapshots"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _raise_if_snapshot_schema_drift(err: Exception) -> None:
    message = str(err)
    if f"{_SCHEMA}.{_TABLE}" not in message or "lease_resource_snapshots" not in message:
        return
    raise RuntimeError(
        "container.resource_snapshots is missing; "
        "stale lease_resource_snapshots residue is not a fallback"
    ) from err


def _t(client: Any) -> Any:
    return q.schema_table(client, _SCHEMA, _TABLE, _REPO)


def upsert_sandbox_resource_snapshot(
    *,
    sandbox_id: str,
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
        raise RuntimeError("upsert_sandbox_resource_snapshot requires a client")
    now = _now_iso()
    try:
        _t(client).upsert(
            {
                "sandbox_id": sandbox_id,
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
    except Exception as err:
        _raise_if_snapshot_schema_drift(err)
        raise


def list_snapshots_by_sandbox_ids(
    sandbox_ids: list[str],
    client: Any = None,
) -> dict[str, dict[str, Any]]:
    if client is None:
        raise RuntimeError("list_snapshots_by_sandbox_ids requires a client")
    if not sandbox_ids:
        return {}
    unique_ids = sorted({sid for sid in sandbox_ids if sid})
    if not unique_ids:
        return {}

    try:
        rows = q.rows_in_chunks(
            lambda: _t(client).select("*"),
            "sandbox_id",
            unique_ids,
            "resource_snapshot",
            "list_by_ids",
        )
    except Exception as err:
        _raise_if_snapshot_schema_drift(err)
        raise
    return {str(r["sandbox_id"]): dict(r) for r in rows}


class SupabaseResourceSnapshotRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def upsert_resource_snapshot_for_sandbox(
        self,
        *,
        sandbox_id: str,
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
        upsert_sandbox_resource_snapshot(
            sandbox_id=sandbox_id,
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
        sandbox_ids: list[str] = []
        for session in sessions:
            sandbox_id = str(session.get("sandbox_id") or "").strip()
            if not sandbox_id or sandbox_id in sandbox_ids:
                continue
            sandbox_ids.append(sandbox_id)

        return list_snapshots_by_sandbox_ids(sandbox_ids, client=self._client)
