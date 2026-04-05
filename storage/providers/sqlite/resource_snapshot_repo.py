"""Resource snapshot repository for SQLite."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_resource_snapshot_table(db_path: Path | None = None) -> None:
    db_path = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
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
    db_path: Path | None = None,
) -> None:
    db_path = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
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


def list_snapshots_by_lease_ids(lease_ids: list[str], db_path: Path | None = None) -> dict[str, dict[str, Any]]:
    db_path = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
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
