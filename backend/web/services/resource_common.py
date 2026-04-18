"""Shared resource helper functions for monitor and product projections."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.web.core.config import SANDBOXES_DIR
from backend.web.services.sandbox_service import build_provider_from_config_name
from sandbox.provider import RESOURCE_CAPABILITY_KEYS
from sandbox.providers.agentbay import AgentBayProvider
from sandbox.providers.daytona import DaytonaProvider
from sandbox.providers.docker import DockerProvider
from sandbox.providers.e2b import E2BProvider
from sandbox.providers.local import LocalSessionProvider
from storage.runtime import build_thread_repo, build_user_repo


@dataclass(frozen=True)
class CatalogEntry:
    vendor: str | None
    description: str
    provider_type: str


CATALOG: dict[str, CatalogEntry] = {
    "local": CatalogEntry(**LocalSessionProvider.CATALOG_ENTRY),
    "docker": CatalogEntry(**DockerProvider.CATALOG_ENTRY),
    "daytona": CatalogEntry(**DaytonaProvider.CATALOG_ENTRY),
    "e2b": CatalogEntry(**E2BProvider.CATALOG_ENTRY),
    "agentbay": CatalogEntry(**AgentBayProvider.CATALOG_ENTRY),
}


def resolve_provider_name(config_name: str, *, sandboxes_dir: Path) -> str:
    payload = _load_sandbox_config(config_name, sandboxes_dir)
    provider = str(payload.get("provider") or "").strip()
    if not provider:
        raise RuntimeError(f"Sandbox config missing provider: {config_name}")
    return provider


def resolve_provider_type(provider_name: str) -> str:
    entry = CATALOG.get(provider_name)
    if not entry:
        raise RuntimeError(f"Unsupported provider type: {provider_name}")
    # @@@daytona-always-cloud - daytona is always "云端" (cloud) regardless of target (cloud/self-host)
    # Both cloud-hosted and self-hosted daytona are conceptually cloud sandboxes from user perspective
    return entry.provider_type


def resolve_console_url(provider_name: str, config_name: str, *, sandboxes_dir: Path) -> str | None:
    payload = _load_sandbox_config(config_name, sandboxes_dir)
    override = str(payload.get("console_url") or "").strip()
    if override:
        return override
    if provider_name == "agentbay":
        return "https://agentbay.console.aliyun.com/overview"
    if provider_name == "e2b":
        return "https://e2b.dev"
    if provider_name == "daytona":
        raw_daytona = payload.get("daytona")
        daytona = raw_daytona if isinstance(raw_daytona, dict) else {}
        target = str(daytona.get("target") or "").strip().lower()
        if target == "cloud":
            return "https://app.daytona.io"
        api_url = str(daytona.get("api_url") or "").strip().rstrip("/")
        return api_url.removesuffix("/api")
    return None


def _load_sandbox_config(config_name: str, sandboxes_dir: Path) -> dict[str, Any]:
    if config_name == "local":
        return {"provider": "local"}
    config_path = sandboxes_dir / f"{config_name}.json"
    payload = json.loads(config_path.read_text())
    if not isinstance(payload, dict):
        raise RuntimeError(f"Sandbox config is not a JSON object: {config_path}")
    return payload


def empty_capabilities() -> dict[str, bool]:
    return {key: False for key in RESOURCE_CAPABILITY_KEYS}


def resolve_instance_capabilities(config_name: str) -> tuple[dict[str, bool], str | None]:
    provider = build_provider_from_config_name(config_name, sandboxes_dir=SANDBOXES_DIR)
    if provider is None:
        return empty_capabilities(), f"Failed to initialize provider instance: {config_name}"
    try:
        normalized = provider.get_capability().declared_resource_capabilities()
    except Exception as exc:
        return empty_capabilities(), f"Failed to read provider capability: {config_name}: {exc}"
    # @@@capability-single-source - read from provider instance to stay aligned with runtime overrides.
    return {key: normalized[key] for key in RESOURCE_CAPABILITY_KEYS}, None


def to_resource_status(available: bool, running_count: int) -> str:
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
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return "stale"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    age_sec = max((datetime.now(UTC) - parsed).total_seconds(), 0.0)
    if age_sec <= 30:
        return "live"
    if age_sec <= 180:
        return "cached"
    return "stale"


def metric(
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


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def to_resource_metrics(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
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


def thread_owners(thread_ids: list[str], user_repo: Any = None, thread_repo: Any = None) -> dict[str, dict[str, str | None]]:
    unique = sorted({tid for tid in thread_ids if tid})
    if not unique:
        return {}

    repo = thread_repo
    own_thread_repo = False
    if repo is None:
        repo = build_thread_repo()
        own_thread_repo = True
    try:
        refs: dict[str, str] = {}
        for data in repo.list_by_ids(unique):
            tid = str(data.get("id") or "").strip()
            if not tid:
                continue
            agent_ref = str(data.get("agent_user_id") or "").strip() if data else ""
            if agent_ref:
                refs[tid] = agent_ref
    finally:
        if own_thread_repo:
            repo.close()

    agent_user_meta: dict[str, dict[str, str | None]] = {}
    if refs:
        repo = user_repo
        own_user_repo = False
        if repo is None:
            repo = build_user_repo()
            own_user_repo = True
        try:
            agent_user_meta = {
                user.id: {
                    "agent_name": user.display_name,
                    "avatar_url": f"/api/users/{user.id}/avatar" if user.id and user.avatar else None,
                }
                for user in repo.list_all()
                if user.id and user.display_name
            }
        finally:
            if own_user_repo:
                repo.close()

    owners: dict[str, dict[str, str | None]] = {}
    for thread_id in thread_ids:
        agent_ref = refs.get(thread_id)
        if not agent_ref:
            owners[thread_id] = {"agent_user_id": None, "agent_name": "未绑定Agent", "avatar_url": None}
            continue
        # @@@agent-name-resolution - current thread agent ref may resolve to an agent user id or direct display name.
        meta = agent_user_meta.get(agent_ref, {})
        owners[thread_id] = {
            "agent_user_id": agent_ref,
            "agent_name": meta.get("agent_name") or agent_ref,
            "avatar_url": meta.get("avatar_url"),
        }
    return owners


def aggregate_provider_telemetry(
    *,
    provider_resource_rows: list[dict[str, Any]],
    running_count: int,
    snapshot_by_sandbox: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    sandbox_ids = sorted(
        {str(resource_row.get("sandbox_id") or "").strip() for resource_row in provider_resource_rows if resource_row.get("sandbox_id")}
    )
    snapshots = [snapshot_by_sandbox[sandbox_id] for sandbox_id in sandbox_ids if sandbox_id in snapshot_by_sandbox]

    freshness = "stale"
    if snapshots:
        latest_collected_at = max(str(snapshot.get("collected_at") or "") for snapshot in snapshots)
        freshness = _to_metric_freshness(latest_collected_at)

    def _sum_snapshot_field(field: str, *, scale: float = 1.0, positive_only: bool = False) -> float | None:
        values = []
        for snapshot in snapshots:
            raw = snapshot.get(field)
            if raw is None:
                continue
            value = float(raw)
            if positive_only and value <= 0:
                continue
            values.append(value / scale)
        return float(sum(values)) if values else None

    cpu_used = _sum_snapshot_field("cpu_used")
    cpu_limit = _sum_snapshot_field("cpu_limit")
    mem_used = _sum_snapshot_field("memory_used_mb", scale=1024.0)
    mem_limit = _sum_snapshot_field("memory_total_mb", scale=1024.0, positive_only=True)
    disk_used = _sum_snapshot_field("disk_used_gb")
    # @@@disk-total-zero-guard - disk_total=0 is physically impossible; treat as missing probe data.
    disk_limit = _sum_snapshot_field("disk_total_gb", positive_only=True)

    has_snapshots = len(snapshots) > 0
    latest_probe_error: str | None = None
    if snapshots:
        latest = max(snapshots, key=lambda item: str(item.get("collected_at") or ""))
        raw_error = str(latest.get("probe_error") or "").strip()
        latest_probe_error = raw_error or None

    def _usage_metric(used: float | None, limit: float | None, unit: str) -> dict[str, Any]:
        has_value = used is not None or limit is not None
        source = "api" if has_value else ("sandbox_db" if has_snapshots else "unknown")
        return metric(used, limit, unit, source, freshness, None if has_value else latest_probe_error)

    return {
        "running": metric(running_count, None, "sandbox", "sandbox_db", "cached"),
        "cpu": _usage_metric(cpu_used, cpu_limit, "%"),
        "memory": _usage_metric(mem_used, mem_limit, "GB"),
        "disk": _usage_metric(disk_used, disk_limit, "GB"),
    }


def resolve_card_cpu_metric(provider_type: str, telemetry: dict[str, Any]) -> dict[str, Any]:
    cpu = dict(telemetry.get("cpu") or {})
    if provider_type == "local":
        return cpu
    # @@@card-cpu-non-local-guardrail - container/cloud providers only have per-sandbox CPU readings,
    # not a provider-level quota. Aggregating sandbox internals on the summary card is misleading.
    cpu["used"] = None
    cpu["limit"] = None
    cpu["source"] = "unknown"
    cpu["error"] = "CPU usage is per-sandbox, not a provider-level quota."
    return cpu
