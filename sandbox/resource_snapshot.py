"""Lease resource snapshot persistence and probing helpers."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sandbox.config import DEFAULT_DB_PATH
from sandbox.provider import SandboxProvider


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def ensure_resource_snapshot_table(db_path: Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lease_resource_snapshots (
                lease_id TEXT PRIMARY KEY,
                provider_name TEXT NOT NULL,
                observed_state TEXT NOT NULL,
                probe_mode TEXT NOT NULL,
                cpu_used REAL,
                cpu_limit REAL,
                memory_used_mb REAL,
                memory_total_mb REAL,
                disk_used_gb REAL,
                disk_total_gb REAL,
                network_rx_kbps REAL,
                network_tx_kbps REAL,
                probe_error TEXT,
                collected_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        conn.commit()


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
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    ensure_resource_snapshot_table(db_path)
    now = _now_iso()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO lease_resource_snapshots (
                lease_id, provider_name, observed_state, probe_mode,
                cpu_used, cpu_limit, memory_used_mb, memory_total_mb,
                disk_used_gb, disk_total_gb, network_rx_kbps, network_tx_kbps,
                probe_error, collected_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lease_id) DO UPDATE SET
                provider_name = excluded.provider_name,
                observed_state = excluded.observed_state,
                probe_mode = excluded.probe_mode,
                cpu_used = excluded.cpu_used,
                cpu_limit = excluded.cpu_limit,
                memory_used_mb = excluded.memory_used_mb,
                memory_total_mb = excluded.memory_total_mb,
                disk_used_gb = excluded.disk_used_gb,
                disk_total_gb = excluded.disk_total_gb,
                network_rx_kbps = excluded.network_rx_kbps,
                network_tx_kbps = excluded.network_tx_kbps,
                probe_error = excluded.probe_error,
                collected_at = excluded.collected_at,
                updated_at = excluded.updated_at
            """,
            (
                lease_id,
                provider_name,
                observed_state,
                probe_mode,
                cpu_used,
                cpu_limit,
                memory_used_mb,
                memory_total_mb,
                disk_used_gb,
                disk_total_gb,
                network_rx_kbps,
                network_tx_kbps,
                probe_error,
                now,
                now,
            ),
        )
        conn.commit()


def probe_and_upsert_for_instance(
    *,
    lease_id: str,
    provider_name: str,
    observed_state: str,
    probe_mode: str,
    provider: SandboxProvider,
    instance_id: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
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
        db_path=db_path,
    )
    return {"ok": probe_error is None, "error": probe_error}


def list_snapshots_by_lease_ids(lease_ids: list[str], db_path: Path = DEFAULT_DB_PATH) -> dict[str, dict[str, Any]]:
    unique_lease_ids = sorted({lease_id for lease_id in lease_ids if lease_id})
    if not unique_lease_ids or not db_path.exists():
        return {}

    placeholders = ",".join(["?"] * len(unique_lease_ids))
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lease_resource_snapshots' LIMIT 1"
        ).fetchone()
        if table is None:
            return {}
        rows = conn.execute(
            f"SELECT * FROM lease_resource_snapshots WHERE lease_id IN ({placeholders})",
            unique_lease_ids,
        ).fetchall()
    return {str(row["lease_id"]): dict(row) for row in rows}
