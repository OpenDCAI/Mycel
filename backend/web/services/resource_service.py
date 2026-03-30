"""Resource overview aggregation and background probe service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.web.core.config import SANDBOXES_DIR
from backend.web.services.config_loader import SandboxConfigLoader
from backend.web.services.sandbox_service import available_sandbox_types, build_provider_from_config_name
from backend.web.utils.serializers import avatar_url
from storage.providers.sqlite.thread_repo import SQLiteThreadRepo
from sandbox.providers.local import LocalSessionProvider
from sandbox.providers.docker import DockerProvider
from sandbox.providers.daytona import DaytonaProvider
from sandbox.providers.e2b import E2BProvider
from sandbox.providers.agentbay import AgentBayProvider
from sandbox.provider import RESOURCE_CAPABILITY_KEYS
from sandbox.resource_snapshot import (
    ensure_resource_snapshot_table,
    list_snapshots_by_lease_ids,
    probe_and_upsert_for_instance,
    upsert_lease_resource_snapshot,
)
from storage.models import map_lease_to_session_status
from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo

_CONFIG_LOADER = SandboxConfigLoader(SANDBOXES_DIR)


# ---------------------------------------------------------------------------
# Provider catalog (display metadata: vendor, description, console URL)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogEntry:
    vendor: str | None
    description: str
    provider_type: str


# Build catalog from provider classes
_CATALOG: dict[str, _CatalogEntry] = {
    "local": _CatalogEntry(**LocalSessionProvider.CATALOG_ENTRY),
    "docker": _CatalogEntry(**DockerProvider.CATALOG_ENTRY),
    "daytona": _CatalogEntry(**DaytonaProvider.CATALOG_ENTRY),
    "e2b": _CatalogEntry(**E2BProvider.CATALOG_ENTRY),
    "agentbay": _CatalogEntry(**AgentBayProvider.CATALOG_ENTRY),
}


def resolve_provider_name(config_name: str, *, sandboxes_dir: Path) -> str:
    return _CONFIG_LOADER.get_provider_name(config_name)


def _resolve_provider_type(provider_name: str, config_name: str, *, sandboxes_dir: Path) -> str:
    entry = _CATALOG.get(provider_name)
    if not entry:
        raise RuntimeError(f"Unsupported provider type: {provider_name}")
    # @@@daytona-always-cloud - daytona is always "云端" (cloud) regardless of target (cloud/self-host)
    # Both cloud-hosted and self-hosted daytona are conceptually cloud sandboxes from user perspective
    return entry.provider_type


def _resolve_console_url(provider_name: str, config_name: str, *, sandboxes_dir: Path) -> str | None:
    payload = _CONFIG_LOADER.load(config_name)
    override = str(payload.get("console_url") or "").strip()
    if override:
        return override
    if provider_name == "agentbay":
        return "https://agentbay.console.aliyun.com/overview"
    if provider_name == "e2b":
        return "https://e2b.dev"
    if provider_name == "daytona":
        daytona = payload.get("daytona") if isinstance(payload.get("daytona"), dict) else {}
        target = str(daytona.get("target") or "").strip().lower()
        if target == "cloud":
            return "https://app.daytona.io"
        api_url = str(daytona.get("api_url") or "").strip().rstrip("/")
        return api_url[:-4] if api_url.endswith("/api") else api_url
    return None


# ---------------------------------------------------------------------------
# Capability helpers
# ---------------------------------------------------------------------------


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
    # @@@capability-single-source - read from provider instance to stay aligned with runtime overrides.
    return {key: normalized[key] for key in RESOURCE_CAPABILITY_KEYS}, None


# ---------------------------------------------------------------------------
# Status/metric helpers
# ---------------------------------------------------------------------------


def _to_resource_status(available: bool, running_count: int) -> str:
    if not available:
        return "unavailable"
    return "active" if running_count > 0 else "ready"


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
        parsed = parsed.replace(tzinfo=UTC)
    age_sec = max((datetime.now(UTC) - parsed).total_seconds(), 0.0)
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


def _to_session_metrics(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not snapshot:
        return None
    cpu = _as_float(snapshot.get("cpu_used"))
    memory_mb = _as_float(snapshot.get("memory_used_mb"))
    memory_total_mb = _as_float(snapshot.get("memory_total_mb"))
    disk_gb = _as_float(snapshot.get("disk_used_gb"))
    disk_total_gb = _as_float(snapshot.get("disk_total_gb"))
    network_rx = _as_float(snapshot.get("network_rx_kbps"))
    network_tx = _as_float(snapshot.get("network_tx_kbps"))
    probe_error = str(snapshot.get("probe_error") or "").strip() or None

    if all(v is None for v in [cpu, memory_mb, memory_total_mb, disk_gb, disk_total_gb]):
        return None

    memory_note: str | None = None
    if memory_total_mb is None:
        memory_note = "no container memory limit configured"

    disk_note: str | None = None
    if disk_gb is None:
        if probe_error:
            disk_note = probe_error
        elif disk_total_gb is not None:
            disk_note = "disk usage not measurable inside container; showing quota only"
        else:
            disk_note = "disk metrics unavailable"

    return {
        "cpu": cpu,
        "memory": (memory_mb / 1024.0) if memory_mb is not None else None,
        "memoryLimit": (memory_total_mb / 1024.0) if memory_total_mb is not None else None,
        "memoryNote": memory_note,
        "disk": disk_gb,
        "diskLimit": disk_total_gb,
        "diskNote": disk_note,
        "networkIn": network_rx,
        "networkOut": network_tx,
        "probeError": probe_error,
    }


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _member_meta_map() -> dict[str, dict[str, str | None]]:
    """Build member_id → display metadata map from DB."""
    try:
        from storage.providers.sqlite.member_repo import SQLiteMemberRepo
        return {
            m.id: {
                "member_name": m.name,
                "avatar_url": avatar_url(m.id, bool(m.avatar)),
            }
            for m in SQLiteMemberRepo().list_all()
            if m.id and m.name
        }
    except Exception:
        return {}


def _thread_agent_refs(thread_ids: list[str]) -> dict[str, str]:
    """Batch lookup agent refs from threads table."""
    unique = sorted({tid for tid in thread_ids if tid})
    if not unique:
        return {}
    repo = SQLiteThreadRepo()
    try:
        refs: dict[str, str] = {}
        for tid in unique:
            data = repo.get_by_id(tid)
            agent_ref = str(data.get("member_id") or "").strip() if data else ""
            if agent_ref:
                refs[tid] = agent_ref
        return refs
    except Exception:
        return {}
    finally:
        repo.close()


def _thread_owners(thread_ids: list[str]) -> dict[str, dict[str, str | None]]:
    refs = _thread_agent_refs(thread_ids)
    member_meta = _member_meta_map()
    owners: dict[str, dict[str, str | None]] = {}
    for thread_id in thread_ids:
        agent_ref = refs.get(thread_id)
        if not agent_ref:
            owners[thread_id] = {"member_id": None, "member_name": "未绑定Agent", "avatar_url": None}
            continue
        # @@@agent-name-resolution - thread_config.agent may be member id or direct display name.
        meta = member_meta.get(agent_ref, {})
        owners[thread_id] = {
            "member_id": agent_ref,
            "member_name": meta.get("member_name") or agent_ref,
            "avatar_url": meta.get("avatar_url"),
        }
    return owners


def _aggregate_provider_telemetry(
    *,
    provider_sessions: list[dict[str, Any]],
    running_count: int,
    snapshot_by_lease: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    lease_ids = sorted({
        str(s.get("lease_id") or "")
        for s in provider_sessions if s.get("lease_id")
    })
    snapshots = [snapshot_by_lease[lid] for lid in lease_ids if lid in snapshot_by_lease]

    freshness = "stale"
    if snapshots:
        latest_collected_at = max(str(snap.get("collected_at") or "") for snap in snapshots)
        freshness = _to_metric_freshness(latest_collected_at)

    cpu_used = _sum_or_none([float(s["cpu_used"]) for s in snapshots if s.get("cpu_used") is not None])
    cpu_limit = _sum_or_none([float(s["cpu_limit"]) for s in snapshots if s.get("cpu_limit") is not None])
    mem_used = _sum_or_none(
        [float(s["memory_used_mb"]) / 1024.0 for s in snapshots if s.get("memory_used_mb") is not None]
    )
    mem_limit = _sum_or_none(
        [float(s["memory_total_mb"]) / 1024.0 for s in snapshots
         if s.get("memory_total_mb") is not None and float(s["memory_total_mb"]) > 0]
    )
    disk_used = _sum_or_none([float(s["disk_used_gb"]) for s in snapshots if s.get("disk_used_gb") is not None])
    # @@@disk-total-zero-guard - disk_total=0 is physically impossible; treat as missing probe data.
    disk_limit = _sum_or_none(
        [float(s["disk_total_gb"]) for s in snapshots
         if s.get("disk_total_gb") is not None and float(s["disk_total_gb"]) > 0]
    )

    has_snapshots = len(snapshots) > 0
    latest_probe_error: str | None = None
    if snapshots:
        latest = max(snapshots, key=lambda item: str(item.get("collected_at") or ""))
        raw_error = str(latest.get("probe_error") or "").strip()
        latest_probe_error = raw_error or None

    def _usage_metric(used: float | None, limit: float | None, unit: str) -> dict[str, Any]:
        has_value = used is not None or limit is not None
        source = "api" if has_value else ("sandbox_db" if has_snapshots else "unknown")
        return _metric(used, limit, unit, source, freshness, None if has_value else latest_probe_error)

    return {
        "running": _metric(running_count, None, "sandbox", "sandbox_db", "cached"),
        "cpu": _usage_metric(cpu_used, cpu_limit, "%"),
        "memory": _usage_metric(mem_used, mem_limit, "GB"),
        "disk": _usage_metric(disk_used, disk_limit, "GB"),
    }


def _resolve_card_cpu_metric(provider_type: str, telemetry: dict[str, Any]) -> dict[str, Any]:
    cpu = dict(telemetry.get("cpu") or {})
    if provider_type == "local":
        # Local = host machine itself; CPU% is meaningful.
        return cpu
    # @@@card-cpu-non-local-guardrail - container/cloud providers only have per-sandbox CPU readings,
    # not a provider-level quota. Aggregating sandbox internals on the summary card is misleading.
    cpu["used"] = None
    cpu["limit"] = None
    cpu["source"] = "unknown"
    cpu["error"] = "CPU usage is per-sandbox, not a provider-level quota."
    return cpu


# ---------------------------------------------------------------------------
# Public API: resource overview
# ---------------------------------------------------------------------------


def list_resource_providers() -> dict[str, Any]:
    # @@@overview-fast-path - avoid provider-network calls; overview uses DB session snapshot.
    repo = SQLiteSandboxMonitorRepo()
    try:
        sessions = repo.list_sessions_with_leases()
    finally:
        repo.close()

    grouped: dict[str, list[dict[str, Any]]] = {}
    for session in sessions:
        # @@@provider-instance-identity - session.provider is config-instance name (not provider kind).
        provider_instance = str(session.get("provider") or "local")
        grouped.setdefault(provider_instance, []).append(session)

    owners = _thread_owners([str(s["thread_id"]) for s in sessions if s.get("thread_id")])
    snapshot_by_lease = list_snapshots_by_lease_ids([str(s.get("lease_id") or "") for s in sessions])

    providers: list[dict[str, Any]] = []
    for item in available_sandbox_types():
        config_name = str(item["name"])
        available = bool(item.get("available"))
        provider_name = resolve_provider_name(config_name, sandboxes_dir=SANDBOXES_DIR)
        catalog = _CATALOG.get(provider_name) or _CatalogEntry(vendor=None, description=provider_name, provider_type="cloud")
        capabilities, capability_error = _resolve_instance_capabilities(config_name)
        effective_available = available and capability_error is None
        unavailable_reason: str | None = None
        if not effective_available:
            unavailable_reason = str(item.get("reason") or capability_error or "provider unavailable")

        provider_sessions = grouped.get(config_name, [])
        normalized_sessions: list[dict[str, Any]] = []
        running_count = 0
        # @@@running-dedup - lease-driven query may yield multiple rows per lease (one per crew member).
        # Count each running lease only once.
        seen_running_leases: set[str] = set()
        for session in provider_sessions:
            # Use unified state mapping logic
            observed_state = session.get("observed_state")
            desired_state = session.get("desired_state")
            normalized = map_lease_to_session_status(observed_state, desired_state)
            thread_id = str(session.get("thread_id") or "")
            lease_id = str(session.get("lease_id") or "")
            if normalized == "running" and lease_id not in seen_running_leases:
                running_count += 1
                seen_running_leases.add(lease_id)
            session_metrics = _to_session_metrics(snapshot_by_lease.get(lease_id))
            owner = owners.get(thread_id, {"member_id": None, "member_name": "未绑定Agent"})
            normalized_sessions.append({
                # @@@resource-session-identity - monitor rows can legitimately have empty chat session ids.
                # Use stable lease+thread identity so React keys do not collapse when one lease has multiple threads.
                "id": str(session.get("session_id") or f"{lease_id}:{thread_id or 'unbound'}"),
                "leaseId": lease_id,
                "threadId": thread_id,
                "memberId": str(owner.get("member_id") or ""),
                "memberName": str(owner.get("member_name") or "未绑定Agent"),
                "avatarUrl": owner.get("avatar_url"),
                "status": normalized,
                "startedAt": str(session.get("created_at") or ""),
                "metrics": session_metrics,
            })

        provider_type = _resolve_provider_type(provider_name, config_name, sandboxes_dir=SANDBOXES_DIR)
        telemetry = _aggregate_provider_telemetry(
            provider_sessions=provider_sessions,
            running_count=running_count,
            snapshot_by_lease=snapshot_by_lease,
        )
        # @@@local-host-metrics - local sessions bypass the probe loop, so fetch host metrics inline.
        # Fast: no network, just shell commands (ps, vm_stat, df).
        if config_name == "local" and effective_available and capabilities.get("metrics"):
            host_m = LocalSessionProvider().get_metrics("host")
            if host_m is not None:
                telemetry = {
                    "running": telemetry["running"],
                    "cpu": _metric(host_m.cpu_percent, None, "%", "direct", "live"),
                    "memory": _metric(
                        host_m.memory_used_mb / 1024.0 if host_m.memory_used_mb is not None else None,
                        host_m.memory_total_mb / 1024.0 if host_m.memory_total_mb is not None else None,
                        "GB", "direct", "live",
                    ),
                    "disk": _metric(host_m.disk_used_gb, host_m.disk_total_gb, "GB", "direct", "live"),
                }
        providers.append({
            "id": config_name,
            "name": config_name,
            "description": catalog.description,
            "vendor": catalog.vendor,
            "type": provider_type,
            "status": _to_resource_status(effective_available, running_count),
            "unavailableReason": unavailable_reason,
            "error": (
                {"code": "PROVIDER_UNAVAILABLE", "message": unavailable_reason} if unavailable_reason else None
            ),
            "capabilities": capabilities,
            "telemetry": telemetry,
            "cardCpu": _resolve_card_cpu_metric(provider_type, telemetry),
            "consoleUrl": _resolve_console_url(provider_name, config_name, sandboxes_dir=SANDBOXES_DIR),
            "sessions": normalized_sessions,
        })

    summary = {
        "snapshot_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "total_providers": len(providers),
        "active_providers": len([p for p in providers if p.get("status") == "active"]),
        "unavailable_providers": len([p for p in providers if p.get("status") == "unavailable"]),
        "running_sessions": sum(
            int((p.get("telemetry") or {}).get("running", {}).get("used") or 0) for p in providers
        ),
    }
    return {"summary": summary, "providers": providers}


# ---------------------------------------------------------------------------
# Public API: sandbox filesystem browse
# ---------------------------------------------------------------------------


def sandbox_browse(lease_id: str, path: str) -> dict[str, Any]:
    """Browse the filesystem of a sandbox lease via its provider."""
    from pathlib import PurePosixPath

    repo = SQLiteSandboxMonitorRepo()
    try:
        lease = repo.query_lease(lease_id)
        instance_id = repo.query_lease_instance_id(lease_id)
    finally:
        repo.close()

    if not lease:
        raise KeyError(f"Lease not found: {lease_id}")

    provider_name = str(lease.get("provider_name") or "").strip()
    if not provider_name:
        raise RuntimeError("Lease has no provider")

    if not instance_id:
        raise RuntimeError("No active instance for this lease — sandbox may be destroyed or paused")

    provider = build_provider_from_config_name(provider_name)
    if provider is None:
        raise RuntimeError(f"Could not initialize provider: {provider_name}")

    try:
        entries = provider.list_dir(instance_id, path)
    except Exception as exc:
        raise RuntimeError(f"Failed to list directory: {exc}") from exc

    norm_path = path if path else "/"

    items = []
    for entry in entries:
        name = str(entry.get("name") or "").strip()
        if not name or name.startswith("."):
            continue
        is_dir = entry.get("type") == "directory"
        child_path = f"{norm_path.rstrip('/')}/{name}"
        items.append({"name": name, "path": child_path, "is_dir": is_dir})

    # Dirs first, then files, each alphabetically
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

    parent = str(PurePosixPath(norm_path).parent)
    parent_path = parent if parent != norm_path else None

    return {"current_path": norm_path, "parent_path": parent_path, "items": items}


_READ_MAX_BYTES = 100 * 1024  # 100 KB


def sandbox_read(lease_id: str, path: str) -> dict[str, Any]:
    """Read a file from a sandbox lease via its provider."""
    repo = SQLiteSandboxMonitorRepo()
    try:
        lease = repo.query_lease(lease_id)
        instance_id = repo.query_lease_instance_id(lease_id)
    finally:
        repo.close()

    if not lease:
        raise KeyError(f"Lease not found: {lease_id}")

    provider_name = str(lease.get("provider_name") or "").strip()
    if not provider_name:
        raise RuntimeError("Lease has no provider")

    if not instance_id:
        raise RuntimeError("No active instance for this lease — sandbox may be destroyed or paused")

    provider = build_provider_from_config_name(provider_name)
    if provider is None:
        raise RuntimeError(f"Could not initialize provider: {provider_name}")

    try:
        content = provider.read_file(instance_id, path)
    except Exception as exc:
        raise RuntimeError(f"Failed to read file: {exc}") from exc

    truncated = False
    if len(content.encode()) > _READ_MAX_BYTES:
        content = content.encode()[:_READ_MAX_BYTES].decode(errors="replace")
        truncated = True

    return {"path": path, "content": content, "truncated": truncated}


# ---------------------------------------------------------------------------
# Public API: resource probe
# ---------------------------------------------------------------------------


def refresh_resource_snapshots() -> dict[str, Any]:
    """Probe active lease instances and upsert resource snapshots."""
    ensure_resource_snapshot_table()
    repo = SQLiteSandboxMonitorRepo()
    try:
        probe_targets = repo.list_probe_targets()
    finally:
        repo.close()

    provider_cache: dict[str, Any] = {}
    probed = 0
    errors = 0
    running_targets = 0
    non_running_targets = 0

    for item in probe_targets:
        lease_id = item["lease_id"]
        provider_key = item["provider_name"]
        instance_id = item["instance_id"]
        status = item["observed_state"]
        # detached means running (not connected to terminal)
        probe_mode = "running_runtime" if status in ("running", "detached") else "non_running_sdk"
        if probe_mode == "running_runtime":
            running_targets += 1
        else:
            non_running_targets += 1

        provider = provider_cache.get(provider_key)
        if provider is None:
            provider = build_provider_from_config_name(provider_key)
            provider_cache[provider_key] = provider
        if provider is None:
            upsert_lease_resource_snapshot(
                lease_id=lease_id,
                provider_name=provider_key,
                observed_state=status,
                probe_mode=probe_mode,
                probe_error=f"provider init failed: {provider_key}",
            )
            errors += 1
            continue

        result = probe_and_upsert_for_instance(
            lease_id=lease_id,
            provider_name=provider_key,
            observed_state=status,
            probe_mode=probe_mode,
            provider=provider,
            instance_id=instance_id,
        )
        probed += 1
        if not result["ok"]:
            errors += 1

    return {
        "probed": probed,
        "errors": errors,
        "running_targets": running_targets,
        "non_running_targets": non_running_targets,
    }
