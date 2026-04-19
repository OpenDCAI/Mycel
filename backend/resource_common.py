"""Shared resource helper functions for monitor and product projections."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.sandbox_paths import SANDBOXES_DIR
from backend.sandbox_provider_factory import build_provider_from_config_name
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
    cpu_values = []
    memory_used = 0.0
    memory_limit = 0.0
    memory_has_value = False
    memory_has_limit = False
    disk_used = 0.0
    disk_limit = 0.0
    disk_has_value = False
    disk_has_limit = False

    for resource_row in provider_resource_rows:
        sandbox_id = str(resource_row.get("sandbox_id") or "").strip()
        snapshot = snapshot_by_sandbox.get(sandbox_id) if sandbox_id else None
        metrics = to_resource_metrics(snapshot)
        if not metrics:
            continue
        cpu = metrics.get("cpu")
        if isinstance(cpu, (int, float)):
            cpu_values.append(float(cpu))
        memory = metrics.get("memory")
        if isinstance(memory, (int, float)):
            memory_used += float(memory)
            memory_has_value = True
        memory_cap = metrics.get("memoryLimit")
        if isinstance(memory_cap, (int, float)):
            memory_limit += float(memory_cap)
            memory_has_limit = True
        disk = metrics.get("disk")
        if isinstance(disk, (int, float)):
            disk_used += float(disk)
            disk_has_value = True
        disk_cap = metrics.get("diskLimit")
        if isinstance(disk_cap, (int, float)):
            disk_limit += float(disk_cap)
            disk_has_limit = True

    avg_cpu = sum(cpu_values) / len(cpu_values) if cpu_values else None
    return {
        "running": metric(running_count, None, "count", "derived", "live"),
        "cpu": metric(avg_cpu, 100.0 if avg_cpu is not None else None, "%", "derived", "live"),
        "memory": metric(memory_used if memory_has_value else None, memory_limit if memory_has_limit else None, "GB", "derived", "live"),
        "disk": metric(disk_used if disk_has_value else None, disk_limit if disk_has_limit else None, "GB", "derived", "live"),
    }


def resolve_card_cpu_metric(provider_type: str, telemetry: dict[str, Any]) -> dict[str, Any] | None:
    if provider_type == "local":
        return telemetry.get("cpu")
    return None
