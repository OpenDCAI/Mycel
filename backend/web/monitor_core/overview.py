"""Resource overview aggregation for monitor core."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.web.core.config import DB_PATH
from backend.web.core.config import SANDBOXES_DIR
from backend.web.services.sandbox_service import available_sandbox_types
from sandbox.db import DEFAULT_DB_PATH
from sandbox.metadata import get_provider_catalog, resolve_console_url, resolve_provider_name, resolve_provider_type
from sandbox.provider import ProviderCapability, RESOURCE_CAPABILITY_KEYS
from sandbox.resource_snapshot import list_snapshots_by_lease_ids

def _declared_capabilities(provider_name: str) -> dict[str, bool]:
    if provider_name == "local":
        from sandbox.local import LocalSessionProvider

        declared = getattr(LocalSessionProvider, "CAPABILITY", None)
    elif provider_name == "docker":
        from sandbox.providers.docker import DockerProvider

        declared = getattr(DockerProvider, "CAPABILITY", None)
    elif provider_name == "e2b":
        from sandbox.providers.e2b import E2BProvider

        declared = getattr(E2BProvider, "CAPABILITY", None)
    elif provider_name == "daytona":
        from sandbox.providers.daytona import DaytonaProvider

        declared = getattr(DaytonaProvider, "CAPABILITY", None)
    elif provider_name == "agentbay":
        from sandbox.providers.agentbay import AgentBayProvider

        declared = getattr(AgentBayProvider, "CAPABILITY", None)
    else:
        raise RuntimeError(f"Unsupported provider type: {provider_name}")

    if not isinstance(declared, ProviderCapability):
        raise RuntimeError(f"Provider {provider_name} missing class CAPABILITY declaration")

    # @@@capability-contract-surface - monitor consumes only agreed capability keys for stable front-end shape.
    normalized = declared.declared_resource_capabilities()
    return {key: normalized[key] for key in RESOURCE_CAPABILITY_KEYS}
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

    sessions: list[dict[str, Any]] = []
    for row in rows:
        sessions.append(
            {
                "provider": row["provider"] or "local",
                "session_id": row["session_id"],
                "thread_id": row["thread_id"],
                "lease_id": row["lease_id"],
                "status": row["status"],
                "created_at": row["created_at"],
            }
        )
    return sessions


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
            owners[thread_id] = {"agent_id": None, "agent_name": "Unknown"}
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
    for snapshot in sorted(snapshots, key=lambda item: str(item.get("collected_at") or "")):
        raw_error = str(snapshot.get("probe_error") or "").strip()
        if raw_error:
            latest_probe_error = raw_error

    cpu_has_value = cpu_used is not None or cpu_limit is not None
    memory_has_value = memory_used_gb is not None or memory_limit_gb is not None
    disk_has_value = disk_used_gb is not None or disk_limit_gb is not None

    cpu_source = "api" if cpu_has_value else ("sandbox_db" if has_snapshots else "unknown")
    memory_source = "api" if memory_has_value else ("sandbox_db" if has_snapshots else "unknown")
    disk_source = "api" if disk_has_value else ("sandbox_db" if has_snapshots else "unknown")

    return {
        "running": _metric(running_count, None, "sandbox", "sandbox_db", "cached"),
        "cpu": _metric(
            cpu_used,
            cpu_limit,
            "cores",
            cpu_source,
            freshness,
            None if cpu_has_value else latest_probe_error,
        ),
        "memory": _metric(
            memory_used_gb,
            memory_limit_gb,
            "GB",
            memory_source,
            freshness,
            None if memory_has_value else latest_probe_error,
        ),
        "disk": _metric(
            disk_used_gb,
            disk_limit_gb,
            "GB",
            disk_source,
            freshness,
            None if disk_has_value else latest_probe_error,
        ),
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

        provider_sessions = grouped_sessions.get(config_name, [])
        normalized_sessions: list[dict[str, Any]] = []
        running_count = 0
        for session in provider_sessions:
            normalized = _to_session_status(session.get("status"))
            if normalized == "running":
                running_count += 1
            thread_id = str(session.get("thread_id") or "")
            owner = owners.get(thread_id, {"agent_id": None, "agent_name": "Unknown"})
            normalized_sessions.append(
                {
                    "id": str(session.get("session_id") or ""),
                    "threadId": thread_id,
                    "agentId": str(owner.get("agent_id") or ""),
                    "agentName": str(owner.get("agent_name") or "Unknown"),
                    "status": normalized,
                    "startedAt": str(session.get("created_at") or ""),
                }
            )

        providers.append(
            {
                "id": config_name,
                "name": config_name,
                "description": catalog.description,
                "vendor": catalog.vendor,
                "type": resolve_provider_type(provider_name, config_name, sandboxes_dir=SANDBOXES_DIR),
                "status": _to_resource_status(available, running_count),
                "unavailableReason": item.get("reason"),
                "error": (
                    {"code": "PROVIDER_UNAVAILABLE", "message": str(item.get("reason"))}
                    if not available and item.get("reason")
                    else None
                ),
                "capabilities": _declared_capabilities(provider_name),
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
