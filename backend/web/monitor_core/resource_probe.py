"""Background probe for lease resource snapshots."""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.web.services.sandbox_service import build_provider_from_config_name
from sandbox.db import DEFAULT_DB_PATH
from sandbox.resource_snapshot import ensure_resource_snapshot_table, probe_and_upsert_for_instance


def _running_lease_instances() -> list[dict[str, str]]:
    if not DEFAULT_DB_PATH.exists():
        return []

    with sqlite3.connect(str(DEFAULT_DB_PATH), timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sandbox_leases' LIMIT 1"
        ).fetchone()
        if table is None:
            return []
        rows = conn.execute(
            """
            SELECT lease_id, provider_name, current_instance_id, observed_state
            FROM sandbox_leases
            WHERE current_instance_id IS NOT NULL
              AND observed_state = 'running'
            ORDER BY updated_at DESC
            """
        ).fetchall()

    instances: list[dict[str, str]] = []
    for row in rows:
        lease_id = str(row["lease_id"] or "").strip()
        provider_name = str(row["provider_name"] or "").strip()
        instance_id = str(row["current_instance_id"] or "").strip()
        observed_state = str(row["observed_state"] or "unknown").strip().lower()
        if not lease_id or not provider_name or not instance_id:
            continue
        instances.append(
            {
                "lease_id": lease_id,
                "provider_name": provider_name,
                "instance_id": instance_id,
                "observed_state": observed_state,
            }
        )
    return instances


def refresh_resource_snapshots() -> dict[str, Any]:
    ensure_resource_snapshot_table()
    running_instances = _running_lease_instances()

    provider_cache: dict[str, Any] = {}
    probed = 0
    errors = 0
    for item in running_instances:
        lease_id = item["lease_id"]
        provider_key = item["provider_name"]
        instance_id = item["instance_id"]
        status = item["observed_state"]

        provider = provider_cache.get(provider_key)
        if provider is None:
            provider = build_provider_from_config_name(provider_key)
            provider_cache[provider_key] = provider
        if provider is None:
            errors += 1
            continue

        result = probe_and_upsert_for_instance(
            lease_id=lease_id,
            provider_name=provider_key,
            observed_state=status,
            probe_mode="running_runtime",
            provider=provider,
            instance_id=instance_id,
        )
        probed += 1
        if not result["ok"]:
            errors += 1

    return {"probed": probed, "errors": errors, "running_leases": len(running_instances)}
