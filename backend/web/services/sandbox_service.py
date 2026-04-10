"""Sandbox management service."""

import logging
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.web.core.config import LOCAL_WORKSPACE_ROOT, SANDBOXES_DIR
from backend.web.utils.helpers import is_virtual_thread_id
from backend.web.utils.serializers import avatar_url
from sandbox.config import SandboxConfig
from sandbox.manager import SandboxManager
from sandbox.provider import ProviderCapability
from sandbox.recipes import default_recipe_id, list_builtin_recipes, normalize_recipe_snapshot, provider_type_from_name
from storage.models import map_lease_to_session_status
from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo

logger = logging.getLogger(__name__)

_SANDBOX_INVENTORY_LOCK = threading.Lock()
_SANDBOX_INVENTORY: tuple[dict[str, Any], dict[str, Any]] | None = None


def _capability_to_dict(capability: ProviderCapability) -> dict[str, Any]:
    return {
        "can_pause": capability.can_pause,
        "can_resume": capability.can_resume,
        "can_destroy": capability.can_destroy,
        "supports_webhook": capability.supports_webhook,
        "supports_status_probe": capability.supports_status_probe,
        "eager_instance_binding": capability.eager_instance_binding,
        "inspect_visible": capability.inspect_visible,
        "runtime_kind": capability.runtime_kind,
        "mount": capability.mount.to_dict(),
    }


def list_default_recipes() -> list[dict[str, Any]]:
    return list_builtin_recipes(available_sandbox_types())


def list_user_leases(
    user_id: str,
    *,
    thread_repo: Any = None,
    user_repo: Any = None,
    main_db_path: str | Path | None = None,
    sandbox_db_path: str | Path | None = None,
    include_runtime_session_id: bool = False,
) -> list[dict[str, Any]]:
    monitor_repo = make_sandbox_monitor_repo()
    if thread_repo is None or user_repo is None:
        raise RuntimeError("thread_repo and user_repo are required for list_user_leases")
    _thread_repo = thread_repo
    _user_repo = user_repo
    own_repos = False
    try:
        threads_by_id = {
            str(thread.get("id") or ""): thread
            for thread in _thread_repo.list_by_owner_user_id(user_id)
            if thread.get("id")
        }
        users_by_id = {
            str(user.id): user
            for user in _user_repo.list_by_owner_user_id(user_id)
        }
        rows = monitor_repo.list_leases_with_threads()
        query_lease_instance_id = getattr(monitor_repo, "query_lease_instance_id", None) if include_runtime_session_id else None
        grouped: dict[str, dict[str, Any]] = {}
        runtime_session_ids: dict[str, str | None] = {}
        for row in rows:
            lease_id = str(row.get("lease_id") or "").strip()
            if not lease_id:
                continue
            runtime_session_id = runtime_session_ids.get(lease_id)
            if lease_id not in runtime_session_ids:
                runtime_session_id = str(row.get("current_instance_id") or "").strip() or None
                if runtime_session_id is None and callable(query_lease_instance_id):
                    runtime_session_id = query_lease_instance_id(lease_id)
                runtime_session_ids[lease_id] = runtime_session_id
            group = grouped.setdefault(
                lease_id,
                {
                    "lease_id": lease_id,
                    "provider_name": str(row.get("provider_name") or "local"),
                    "recipe_id": str(row.get("recipe_id") or "") or None,
                    "recipe": row.get("recipe_json"),
                    "observed_state": row.get("observed_state"),
                    "desired_state": row.get("desired_state"),
                    "created_at": row.get("created_at"),
                    "cwd": row.get("cwd"),
                    "thread_ids": [],
                    "agents": [],
                },
            )
            if include_runtime_session_id and runtime_session_id and not group.get("runtime_session_id"):
                group["runtime_session_id"] = runtime_session_id
            thread_id = str(row.get("thread_id") or "").strip()
            if not _is_user_visible_lease_thread(thread_id) or thread_id in group["thread_ids"]:
                continue
            thread = threads_by_id.get(thread_id)
            if thread is None:
                continue
            agent_user_id = str(thread.get("agent_user_id") or "").strip()
            if not agent_user_id:
                continue
            agent_user = users_by_id.get(agent_user_id)
            if agent_user is None:
                continue
            group["thread_ids"].append(thread_id)
            group["agents"].append(
                {
                    "thread_id": thread_id,
                    "agent_user_id": agent_user_id,
                    "agent_name": agent_user.display_name,
                    "avatar_url": avatar_url(agent_user.id, bool(agent_user.avatar)),
                }
            )
            if not group["cwd"] and row.get("cwd"):
                group["cwd"] = row.get("cwd")

        leases: list[dict[str, Any]] = []
        for lease in grouped.values():
            if not lease["thread_ids"]:
                continue
            if not _is_user_visible_lease_state(lease):
                continue
            provider_name = lease["provider_name"]
            provider_type = provider_type_from_name(provider_name)
            if lease["recipe"]:
                import json

                recipe_snapshot = normalize_recipe_snapshot(provider_type, json.loads(str(lease["recipe"])))
            else:
                recipe_snapshot = normalize_recipe_snapshot(provider_type)
            lease["recipe_id"] = recipe_snapshot["id"] or lease["recipe_id"] or default_recipe_id(provider_type)
            lease["recipe"] = recipe_snapshot
            lease["recipe_name"] = recipe_snapshot["name"]
            leases.append(lease)
        return leases
    finally:
        if own_repos:
            _user_repo.close()
            _thread_repo.close()
        monitor_repo.close()


def resolve_owned_lease(
    user_id: str,
    lease_id: str,
    *,
    thread_repo: Any = None,
    user_repo: Any = None,
) -> dict[str, Any] | None:
    monitor_repo = make_sandbox_monitor_repo()
    if thread_repo is None or user_repo is None:
        raise RuntimeError("thread_repo and user_repo are required for resolve_owned_lease")
    _thread_repo = thread_repo
    _user_repo = user_repo
    try:
        lease = monitor_repo.query_lease(lease_id)
        if lease is None:
            return None
        if not _is_user_visible_lease_state(lease):
            return None

        thread_ids: list[str] = []
        agents: list[dict[str, Any]] = []
        for row in monitor_repo.query_lease_threads(lease_id):
            thread_id = str(row.get("thread_id") or "").strip()
            if not _is_user_visible_lease_thread(thread_id) or thread_id in thread_ids:
                continue
            thread = _thread_repo.get_by_id(thread_id)
            if thread is None:
                continue
            agent_user_id = str(thread.get("agent_user_id") or "").strip()
            if not agent_user_id:
                continue
            agent_user = _user_repo.get_by_id(agent_user_id)
            if agent_user is None or agent_user.owner_user_id != user_id:
                continue
            thread_ids.append(thread_id)
            agents.append(
                {
                    "thread_id": thread_id,
                    "agent_user_id": agent_user_id,
                    "agent_name": agent_user.display_name,
                    "avatar_url": avatar_url(agent_user.id, bool(agent_user.avatar)),
                }
            )
        if not thread_ids:
            return None

        provider_name = str(lease.get("provider_name") or "local")
        provider_type = provider_type_from_name(provider_name)
        if lease.get("recipe_json"):
            import json

            recipe_snapshot = normalize_recipe_snapshot(provider_type, json.loads(str(lease["recipe_json"])))
        else:
            recipe_snapshot = normalize_recipe_snapshot(provider_type)

        result = dict(lease)
        result["lease_id"] = lease_id
        result["provider_name"] = provider_name
        result["thread_ids"] = thread_ids
        result["agents"] = agents
        result["recipe_id"] = recipe_snapshot["id"] or result.get("recipe_id") or default_recipe_id(provider_type)
        result["recipe"] = recipe_snapshot
        result["recipe_name"] = recipe_snapshot["name"]
        query_lease_instance_id = getattr(monitor_repo, "query_lease_instance_id", None)
        if callable(query_lease_instance_id):
            runtime_session_id = query_lease_instance_id(lease_id)
            if runtime_session_id:
                result["runtime_session_id"] = runtime_session_id
        return result
    finally:
        monitor_repo.close()


def _is_user_visible_lease_thread(thread_id: str | None) -> bool:
    raw = str(thread_id or "").strip()
    if not raw:
        return False
    if raw.startswith("subagent-"):
        return False
    if is_virtual_thread_id(raw):
        return False
    return True


def _is_user_visible_lease_state(lease: dict[str, Any]) -> bool:
    # @@@user-visible-lease-scope - product-facing lease surfaces should only
    # expose leases the user can still act on, not historical stopped/destroying
    # residue from monitor storage.
    status = map_lease_to_session_status(lease.get("observed_state"), lease.get("desired_state"))
    return status in {"running", "paused"}


def available_sandbox_types() -> list[dict[str, Any]]:
    """Scan ~/.leon/sandboxes/ for configured providers."""
    providers, _ = init_providers_and_managers()
    local_capability = providers["local"].get_capability()
    types = [
        {
            "name": "local",
            "provider": "local",
            "available": True,
            "capability": _capability_to_dict(local_capability),
        }
    ]
    if not SANDBOXES_DIR.exists():
        return types
    for f in sorted(SANDBOXES_DIR.glob("*.json")):
        name = f.stem
        try:
            config = SandboxConfig.load(name)
            provider_obj = providers.get(name)
            if provider_obj is None:
                types.append(
                    {
                        "name": name,
                        "provider": config.provider,
                        "available": False,
                        "reason": f"Provider {name} is configured but unavailable in the current process",
                    }
                )
                continue
            item: dict[str, Any] = {
                "name": name,
                "provider": config.provider,
                "available": True,
            }
            if provider_obj:
                item["capability"] = _capability_to_dict(provider_obj.get_capability())
            types.append(item)
        except Exception as e:
            types.append({"name": name, "available": False, "reason": str(e)})
    return types


def init_providers_and_managers() -> tuple[dict, dict]:
    """Load sandbox providers and managers from config files."""
    global _SANDBOX_INVENTORY
    with _SANDBOX_INVENTORY_LOCK:
        if _SANDBOX_INVENTORY is None:
            # @@@sandbox-inventory-singleton - provider configs are process-lifetime state in local dev.
            # Build once and reuse so every API path does not rescan configs and re-instantiate failing providers.
            _SANDBOX_INVENTORY = _build_providers_and_managers()
        return _SANDBOX_INVENTORY


def _build_providers_and_managers() -> tuple[dict[str, Any], dict[str, Any]]:
    """Build sandbox providers/managers exactly once per process."""
    from sandbox.providers.local import LocalSessionProvider

    providers: dict[str, Any] = {
        "local": LocalSessionProvider(default_cwd=str(LOCAL_WORKSPACE_ROOT)),
    }
    if not SANDBOXES_DIR.exists():
        managers = {name: SandboxManager(provider=p) for name, p in providers.items()}
        return providers, managers

    for config_file in SANDBOXES_DIR.glob("*.json"):
        name = config_file.stem
        try:
            config = SandboxConfig.load(name)
            if config.provider == "agentbay":
                from sandbox.providers.agentbay import AgentBayProvider

                key = config.agentbay.api_key or os.getenv("AGENTBAY_API_KEY")
                if not key:
                    logger.warning("[sandbox] %s configured but no API key; skipping", name)
                    continue
                providers[name] = AgentBayProvider(
                    api_key=key,
                    region_id=config.agentbay.region_id,
                    default_context_path=config.agentbay.context_path,
                    image_id=config.agentbay.image_id,
                    provider_name=name,
                    supports_pause=config.agentbay.supports_pause,
                    supports_resume=config.agentbay.supports_resume,
                )
            elif config.provider == "docker":
                from sandbox.providers.docker import DockerProvider

                providers[name] = DockerProvider(
                    image=config.docker.image,
                    mount_path=config.docker.mount_path,
                    default_cwd=config.docker.cwd,
                    bind_mounts=config.docker.bind_mounts,
                    provider_name=name,
                )
            elif config.provider == "e2b":
                from sandbox.providers.e2b import E2BProvider

                key = config.e2b.api_key or os.getenv("E2B_API_KEY")
                if not key:
                    logger.warning("[sandbox] %s configured but no API key; skipping", name)
                    continue
                providers[name] = E2BProvider(
                    api_key=key,
                    template=config.e2b.template,
                    default_cwd=config.e2b.cwd,
                    timeout=config.e2b.timeout,
                    provider_name=name,
                )
            elif config.provider == "daytona":
                from sandbox.providers.daytona import DaytonaProvider

                key = config.daytona.api_key or os.getenv("DAYTONA_API_KEY")
                if not key:
                    logger.warning("[sandbox] %s configured but no API key; skipping", name)
                    continue
                providers[name] = DaytonaProvider(
                    api_key=key,
                    api_url=config.daytona.api_url,
                    target=config.daytona.target,
                    default_cwd=config.daytona.cwd,
                    bind_mounts=config.daytona.bind_mounts,
                    provider_name=name,
                )
        except Exception:
            logger.exception("[sandbox] Failed to load %s", name)

    managers = {name: SandboxManager(provider=p) for name, p in providers.items()}
    return providers, managers


def load_all_sessions(managers: dict) -> list[dict]:
    """Load sessions from all managers in parallel."""
    sessions: list[dict] = []
    if not managers:
        return sessions
    for provider_name, manager in managers.items():
        rows = manager.list_sessions()
        for row in rows:
            sessions.append(
                {
                    "session_id": row["session_id"],
                    "thread_id": row["thread_id"],
                    "provider": row.get("provider", provider_name),
                    "status": row.get("status", "running"),
                    "created_at": row.get("created_at"),
                    "last_active": row.get("last_active"),
                    "lease_id": row.get("lease_id"),
                    "instance_id": row.get("instance_id"),
                    "chat_session_id": row.get("chat_session_id"),
                    "source": row.get("source", "unknown"),
                    "inspect_visible": row.get("inspect_visible", True),
                }
            )

    # @@@stable-session-order - Keep deterministic ordering across refreshes/providers.
    def _to_ts(value: Any) -> float:
        if not value or not isinstance(value, str):
            return 0.0
        try:
            return datetime.fromisoformat(value).timestamp()
        except Exception:
            return 0.0

    sessions.sort(
        key=lambda row: (
            -_to_ts(row.get("created_at")),
            -_to_ts(row.get("last_active")),
            str(row.get("provider") or ""),
            str(row.get("thread_id") or ""),
            str(row.get("session_id") or ""),
        )
    )
    return sessions


def find_session_and_manager(
    sessions: list[dict],
    managers: dict,
    session_id: str,
    provider_name: str | None = None,
) -> tuple[dict | None, Any | None]:
    """Find session by ID/prefix (+optional provider), return (session, manager)."""
    candidates: list[dict] = []
    for s in sessions:
        if provider_name and s.get("provider") != provider_name:
            continue
        sid = str(s.get("session_id") or "")
        if sid == session_id or sid.startswith(session_id):
            candidates.append(s)
    if not candidates:
        return None, None
    if len(candidates) == 1:
        chosen = candidates[0]
        return chosen, managers.get(chosen["provider"])
    exact = [s for s in candidates if str(s.get("session_id") or "") == session_id]
    if len(exact) == 1:
        chosen = exact[0]
        return chosen, managers.get(chosen["provider"])
    raise RuntimeError(f"Ambiguous session_id '{session_id}'. Specify provider query param.")


def mutate_sandbox_session(
    *,
    session_id: str,
    action: str,
    provider_hint: str | None = None,
) -> dict[str, Any]:
    """Perform pause/resume/destroy action on a sandbox session."""
    _, managers = init_providers_and_managers()
    sessions = load_all_sessions(managers)
    session, manager = find_session_and_manager(sessions, managers, session_id, provider_name=provider_hint)
    if not session:
        raise RuntimeError(f"Session not found: {session_id}")

    provider_name = str(session.get("provider") or "")
    if not manager:
        raise RuntimeError(f"Provider manager unavailable: {provider_name}")

    thread_id = str(session.get("thread_id") or "")
    lease_id = session.get("lease_id")
    target_session_id = str(session.get("session_id") or session_id)

    ok = False
    mode = "lease_enforced"

    if manager and thread_id and not is_virtual_thread_id(thread_id):
        mode = "manager_thread"
        if action == "pause":
            ok = manager.pause_session(thread_id)
        elif action == "resume":
            ok = manager.resume_session(thread_id)
        elif action == "destroy":
            ok = manager.destroy_session(thread_id)
        else:
            raise RuntimeError(f"Unknown action: {action}")
    else:
        lease = manager.get_lease(lease_id) if lease_id else None
        if not lease:
            adopt_lease_id = str(lease_id or f"lease-adopt-{uuid.uuid4().hex[:12]}")
            adopt_status = str(session.get("status") or "unknown")
            from sandbox.lease import lease_from_row

            adopt_row = manager.lease_store.adopt_instance(
                lease_id=adopt_lease_id,
                provider_name=provider_name,
                instance_id=target_session_id,
                status=adopt_status,
            )
            lease = lease_from_row(adopt_row, manager.lease_store.db_path)
            lease_id = lease.lease_id

        mode = "manager_lease"
        if action == "pause":
            ok = lease.pause_instance(manager.provider, source="api")
        elif action == "resume":
            ok = lease.resume_instance(manager.provider, source="api")
        elif action == "destroy":
            lease.destroy_instance(manager.provider, source="api")
            ok = True
        else:
            raise RuntimeError(f"Unknown action: {action}")

    if not ok:
        raise RuntimeError(f"Failed to {action} session {target_session_id}")

    return {
        "ok": True,
        "action": action,
        "session_id": target_session_id,
        "provider": provider_name,
        "thread_id": thread_id or None,
        "lease_id": lease_id,
        "mode": mode,
    }


def get_session_metrics(session_id: str, provider_hint: str | None = None) -> dict[str, Any]:
    """Load one session's provider metrics through the current manager inventory."""
    _, managers = init_providers_and_managers()
    sessions = load_all_sessions(managers)
    session, manager = find_session_and_manager(sessions, managers, session_id, provider_name=provider_hint)
    if not session:
        raise RuntimeError(f"Session not found: {session_id}")
    if manager is None:
        raise RuntimeError(f"Provider manager unavailable: {session.get('provider')}")

    target_session_id = str(session.get("instance_id") or session.get("session_id") or session_id)
    metrics = manager.provider.get_metrics(target_session_id)
    if metrics is None:
        return {"session_id": target_session_id, "provider": session.get("provider"), "metrics": None}
    return {
        "session_id": target_session_id,
        "provider": session.get("provider"),
        "metrics": {
            "cpu_percent": metrics.cpu_percent,
            "memory_used_mb": metrics.memory_used_mb,
            "memory_total_mb": metrics.memory_total_mb,
            "disk_used_gb": metrics.disk_used_gb,
            "disk_total_gb": metrics.disk_total_gb,
            "network_rx_kbps": metrics.network_rx_kbps,
            "network_tx_kbps": metrics.network_tx_kbps,
        },
    }


def build_provider_from_config_name(name: str, *, sandboxes_dir: Path | None = None) -> Any | None:
    """Build one provider instance from sandbox config name. Used by resource_service for per-session ops."""
    providers, _ = init_providers_and_managers()
    if name in providers:
        return providers[name]
    _sandboxes_dir = sandboxes_dir or SANDBOXES_DIR
    config_path = _sandboxes_dir / f"{name}.json"
    if not config_path.exists():
        return None
    logger.warning("[sandbox] provider %s is configured but unavailable in the current process", name)
    return None


def destroy_thread_resources_sync(thread_id: str, sandbox_type: str, agent_pool: dict) -> bool:
    """Destroy sandbox resources for a thread."""
    pool_key = f"{thread_id}:{sandbox_type}"
    pooled_agent = agent_pool.get(pool_key)
    if pooled_agent and hasattr(pooled_agent, "_sandbox"):
        manager = pooled_agent._sandbox.manager
    else:
        _, managers = init_providers_and_managers()
        manager = managers.get(sandbox_type)
    if not manager:
        raise RuntimeError(f"No sandbox manager found for provider {sandbox_type}")
    return manager.destroy_thread_resources(thread_id)
