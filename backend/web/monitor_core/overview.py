"""Resource overview aggregation for monitor core."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.web.core.config import DB_PATH
from backend.web.core.config import SANDBOXES_DIR
from backend.web.services.sandbox_service import available_sandbox_types, build_provider_from_config_name
from sandbox.db import DEFAULT_DB_PATH
from sandbox.metadata import get_provider_catalog, resolve_console_url, resolve_provider_name, resolve_provider_type
from sandbox.provider import RESOURCE_CAPABILITY_KEYS
from sandbox.resource_snapshot import list_snapshots_by_lease_ids


def _empty_capabilities() -> dict[str, bool]:
    return {key: False for key in RESOURCE_CAPABILITY_KEYS}


def _resolve_instance_capabilities(config_name: str) -> tuple[dict[str, bool], str | None]:
    provider = build_provider_from_config_name(config_name, sandboxes_dir=SANDBOXES_DIR)
    if provider is None:
        return _empty_capabilities(), f"Failed to initialize provider instance: {config_name}"
    try:
        normalized = provider.get_capability().declared_resource_capabilities()
    except Exception as exc:
        return _empty_capabilities(), f"Failed to read provider capability: {config_name}: {exc}"
    # @@@capability-single-source - monitor must read capability from provider instance to stay aligned with runtime overrides.
    return {key: normalized[key] for key in RESOURCE_CAPABILITY_KEYS}, None


def _to_resource_status(available: bool, running_count: int) -> str:
    if not available:
        return "unavailable"
    return "active" if running_count > 0 else "ready"


def _to_session_status(raw_status: str | None) -> str:
    status = (raw_status or "").strip().lower()
    if status == "paused":
        return "paused"
    if status in {"destroyed", "stopped", "closed", "terminated", "error"}:
        return "stopped"
    return "running"


def _to_metric_freshness(collected_at: str | None) -> str:
    if not collected_at:
        return "stale"
    raw = str(collected_at).strip()
    if not raw:
        return "stale"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return "stale"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_sec = max((datetime.now(timezone.utc) - parsed).total_seconds(), 0.0)
    if age_sec <= 30:
        return "live"
    if age_sec <= 180:
        return "cached"
    return "stale"


def _metric(
    used: float | int | None,
    limit: float | int | None,
    unit: str,
    source: str,
    freshness: str,
    error: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "used": used,
        "limit": limit,
        "unit": unit,
        "source": source,
        "freshness": freshness,
    }
    if error:
        payload["error"] = error
    return payload


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _list_sessions_fast() -> list[dict[str, Any]]:
    if not DEFAULT_DB_PATH.exists():
        return []

    with sqlite3.connect(str(DEFAULT_DB_PATH), timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "chat_sessions"):
            return []
        if not _table_exists(conn, "sandbox_leases"):
            return []

        rows = conn.execute(
            """
            SELECT
                cs.chat_session_id AS session_id,
                cs.thread_id AS thread_id,
                cs.lease_id AS lease_id,
                cs.status AS status,
                cs.started_at AS created_at,
                sl.provider_name AS provider
            FROM chat_sessions cs
            LEFT JOIN sandbox_leases sl ON cs.lease_id = sl.lease_id
            ORDER BY cs.started_at DESC
            """
        ).fetchall()

    return [
        {
            "provider": row["provider"] or "local",
            "session_id": row["session_id"],
            "thread_id": row["thread_id"],
            "lease_id": row["lease_id"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _member_name_map() -> dict[str, str]:
    try:
        from backend.web.services.member_service import list_members

        members = list_members()
    except Exception:
        return {}

    mapping: dict[str, str] = {}
    for member in members:
        member_id = str(member.get("id") or "").strip()
        member_name = str(member.get("name") or "").strip()
        if member_id and member_name:
            mapping[member_id] = member_name
    return mapping


def _thread_agent_refs(thread_ids: list[str]) -> dict[str, str]:
    unique_thread_ids = sorted({tid for tid in thread_ids if tid})
    if not unique_thread_ids or not DB_PATH.exists():
        return {}

    placeholders = ",".join(["?"] * len(unique_thread_ids))
    with sqlite3.connect(str(DB_PATH), timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='thread_config' LIMIT 1"
        ).fetchone()
        if table is None:
            return {}

        rows = conn.execute(
            f"SELECT thread_id, agent FROM thread_config WHERE thread_id IN ({placeholders})",
            unique_thread_ids,
        ).fetchall()

    refs: dict[str, str] = {}
    for row in rows:
        thread_id = str(row["thread_id"] or "").strip()
        agent_ref = str(row["agent"] or "").strip()
        if thread_id and agent_ref:
            refs[thread_id] = agent_ref
    return refs


def _thread_owners(thread_ids: list[str]) -> dict[str, dict[str, str | None]]:
    refs = _thread_agent_refs(thread_ids)
    member_names = _member_name_map()

    owners: dict[str, dict[str, str | None]] = {}
    for thread_id in thread_ids:
        agent_ref = refs.get(thread_id)
        if not agent_ref:
            owners[thread_id] = {"agent_id": None, "agent_name": "未绑定Agent"}
            continue

        # @@@agent-name-resolution - thread_config.agent may be member id or direct display name.
        owners[thread_id] = {
            "agent_id": agent_ref,
            "agent_name": member_names.get(agent_ref, agent_ref),
        }
    return owners


def _sum_or_none(values: list[float | int]) -> float | None:
    if not values:
        return None
    return float(sum(values))


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _to_session_metrics(snapshot: dict[str, Any] | None) -> dict[str, float | None] | None:
    if not snapshot:
        return None
    cpu = _as_float(snapshot.get("cpu_used"))
    memory_mb = _as_float(snapshot.get("memory_used_mb"))
    disk_gb = _as_float(snapshot.get("disk_used_gb"))
    network_rx = _as_float(snapshot.get("network_rx_kbps"))
    network_tx = _as_float(snapshot.get("network_tx_kbps"))
    if cpu is None and memory_mb is None and disk_gb is None and network_rx is None and network_tx is None:
        return None
    return {
        "cpu": cpu,
        "memory": (memory_mb / 1024.0) if memory_mb is not None else None,
        "disk": disk_gb,
        "networkIn": network_rx,
        "networkOut": network_tx,
    }


def _aggregate_provider_telemetry(
    *,
    provider_sessions: list[dict[str, Any]],
    running_count: int,
    snapshot_by_lease: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    lease_ids = sorted({str(session.get("lease_id") or "") for session in provider_sessions if session.get("lease_id")})
    snapshots = [snapshot_by_lease[lease_id] for lease_id in lease_ids if lease_id in snapshot_by_lease]

    freshness = "stale"
    if snapshots:
        latest_collected_at = max(str(snap.get("collected_at") or "") for snap in snapshots)
        freshness = _to_metric_freshness(latest_collected_at)

    cpu_used = _sum_or_none([float(s["cpu_used"]) for s in snapshots if s.get("cpu_used") is not None])
    cpu_limit = _sum_or_none([float(s["cpu_limit"]) for s in snapshots if s.get("cpu_limit") is not None])
    memory_used_gb = _sum_or_none([float(s["memory_used_mb"]) / 1024.0 for s in snapshots if s.get("memory_used_mb") is not None])
    memory_limit_gb = _sum_or_none(
        [float(s["memory_total_mb"]) / 1024.0 for s in snapshots if s.get("memory_total_mb") is not None]
    )
    disk_used_gb = _sum_or_none([float(s["disk_used_gb"]) for s in snapshots if s.get("disk_used_gb") is not None])
    disk_limit_gb = _sum_or_none([float(s["disk_total_gb"]) for s in snapshots if s.get("disk_total_gb") is not None])

    has_snapshots = len(snapshots) > 0
    latest_probe_error: str | None = None
    if snapshots:
        latest_snapshot = max(snapshots, key=lambda item: str(item.get("collected_at") or ""))
        raw_error = str(latest_snapshot.get("probe_error") or "").strip()
        latest_probe_error = raw_error or None

    def _usage_metric(used: float | None, limit: float | None, unit: str) -> dict[str, Any]:
        has_value = used is not None or limit is not None
        source = "api" if has_value else ("sandbox_db" if has_snapshots else "unknown")
        return _metric(used, limit, unit, source, freshness, None if has_value else latest_probe_error)

    return {
        "running": _metric(running_count, None, "sandbox", "sandbox_db", "cached"),
        "cpu": _usage_metric(cpu_used, cpu_limit, "%"),
        "memory": _usage_metric(memory_used_gb, memory_limit_gb, "GB"),
        "disk": _usage_metric(disk_used_gb, disk_limit_gb, "GB"),
    }


def list_resource_providers() -> dict[str, Any]:
    # @@@overview-fast-path - avoid provider-network calls; overview uses DB session snapshot.
    sessions = _list_sessions_fast()
    grouped_sessions: dict[str, list[dict[str, Any]]] = {}
    for session in sessions:
        # @@@provider-instance-identity - session.provider is config-instance name (not provider kind).
        provider_instance = str(session.get("provider") or "local")
        grouped_sessions.setdefault(provider_instance, []).append(session)

    owners = _thread_owners([str(session.get("thread_id") or "") for session in sessions])
    snapshot_by_lease = list_snapshots_by_lease_ids([str(session.get("lease_id") or "") for session in sessions])

    providers: list[dict[str, Any]] = []
    for item in available_sandbox_types():
        config_name = str(item["name"])
        available = bool(item.get("available"))
        provider_name = resolve_provider_name(config_name, sandboxes_dir=SANDBOXES_DIR)
        catalog = get_provider_catalog(provider_name)
        capabilities, capability_error = _resolve_instance_capabilities(config_name)
        effective_available = available and capability_error is None
        unavailable_reason: str | None = None
        if not effective_available:
            unavailable_reason = str(item.get("reason") or capability_error or "provider unavailable")

        provider_sessions = grouped_sessions.get(config_name, [])
        normalized_sessions: list[dict[str, Any]] = []
        running_count = 0
        for session in provider_sessions:
            normalized = _to_session_status(session.get("status"))
            if normalized == "running":
                running_count += 1
            thread_id = str(session.get("thread_id") or "")
            lease_id = str(session.get("lease_id") or "")
            session_metrics = _to_session_metrics(snapshot_by_lease.get(lease_id))
            owner = owners.get(thread_id, {"agent_id": None, "agent_name": "未绑定Agent"})
            normalized_sessions.append(
                {
                    "id": str(session.get("session_id") or ""),
                    "leaseId": lease_id,
                    "threadId": thread_id,
                    "agentId": str(owner.get("agent_id") or ""),
                    "agentName": str(owner.get("agent_name") or "未绑定Agent"),
                    "status": normalized,
                    "startedAt": str(session.get("created_at") or ""),
                    "metrics": session_metrics,
                }
            )

        providers.append(
            {
                "id": config_name,
                "name": config_name,
                "description": catalog.description,
                "vendor": catalog.vendor,
                "type": resolve_provider_type(provider_name, config_name, sandboxes_dir=SANDBOXES_DIR),
                "status": _to_resource_status(effective_available, running_count),
                "unavailableReason": unavailable_reason,
                "error": (
                    {"code": "PROVIDER_UNAVAILABLE", "message": unavailable_reason} if unavailable_reason else None
                ),
                "capabilities": capabilities,
                "telemetry": _aggregate_provider_telemetry(
                    provider_sessions=provider_sessions,
                    running_count=running_count,
                    snapshot_by_lease=snapshot_by_lease,
                ),
                "consoleUrl": resolve_console_url(provider_name, config_name, sandboxes_dir=SANDBOXES_DIR),
                "sessions": normalized_sessions,
            }
        )

    summary = {
        "snapshot_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_providers": len(providers),
        "active_providers": len([p for p in providers if p.get("status") == "active"]),
        "unavailable_providers": len([p for p in providers if p.get("status") == "unavailable"]),
        "running_sessions": sum(int((p.get("telemetry") or {}).get("running", {}).get("used") or 0) for p in providers),
    }

    return {"summary": summary, "providers": providers}
