"""Sandbox management service."""

import json
import logging
import os
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.web.core.config import LOCAL_WORKSPACE_ROOT, SANDBOXES_DIR
from backend.web.services.thread_visibility import canonical_owner_threads
from backend.web.utils.helpers import is_virtual_thread_id
from backend.web.utils.serializers import avatar_url
from sandbox.config import SandboxConfig
from sandbox.manager import SandboxManager
from sandbox.provider import ProviderCapability
from sandbox.recipes import default_recipe_id, list_builtin_recipes, normalize_recipe_snapshot, provider_type_from_name
from storage.models import map_sandbox_state_to_display_status
from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo
from storage.runtime import build_storage_container

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


def _sandbox_agent_payload(thread_id: str, agent_user_id: str, agent_user: Any) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "agent_user_id": agent_user_id,
        "agent_name": agent_user.display_name,
        "avatar_url": avatar_url(agent_user.id, bool(agent_user.avatar)),
    }


def _apply_sandbox_recipe(sandbox_row: dict[str, Any], provider_name: str, raw_recipe: Any) -> None:
    provider_type = provider_type_from_name(provider_name)
    recipe_snapshot = (
        normalize_recipe_snapshot(provider_type, json.loads(str(raw_recipe)), provider_name=provider_name)
        if raw_recipe
        else normalize_recipe_snapshot(provider_type, provider_name=provider_name)
    )
    sandbox_row["recipe_id"] = recipe_snapshot["id"] or sandbox_row.get("recipe_id") or default_recipe_id(provider_name)
    sandbox_row["recipe"] = recipe_snapshot
    sandbox_row["recipe_name"] = recipe_snapshot["name"]


def _configured_api_key(name: str, configured: str | None, env_name: str) -> str | None:
    key = configured or os.getenv(env_name)
    if not key:
        logger.warning("[sandbox] %s configured but no API key; skipping", name)
        return None
    return key


def list_default_recipes() -> list[dict[str, Any]]:
    return list_builtin_recipes(available_sandbox_types())


def _list_user_runtime_rows(
    user_id: str,
    *,
    thread_repo: Any = None,
    user_repo: Any = None,
    include_runtime_session_id: bool = False,
) -> list[dict[str, Any]]:
    monitor_repo = make_sandbox_monitor_repo()
    if thread_repo is None or user_repo is None:
        raise RuntimeError("thread_repo and user_repo are required for user sandbox runtime rows")
    try:
        threads_by_id = {str(thread.get("id") or ""): thread for thread in thread_repo.list_by_owner_user_id(user_id) if thread.get("id")}
        users_by_id = {str(user.id): user for user in user_repo.list_by_owner_user_id(user_id)}
        rows = monitor_repo.query_sandboxes()
        grouped: dict[str, dict[str, Any]] = {}
        runtime_session_ids: dict[str, str | None] = {}
        for row in rows:
            sandbox_id = str(row.get("sandbox_id") or "").strip()
            if not sandbox_id:
                continue
            runtime_session_id = runtime_session_ids.get(sandbox_id)
            if sandbox_id not in runtime_session_ids:
                runtime_session_id = str(row.get("current_instance_id") or "").strip() or None
                if include_runtime_session_id and runtime_session_id is None:
                    runtime_session_id = monitor_repo.query_sandbox_instance_id(sandbox_id)
                runtime_session_ids[sandbox_id] = runtime_session_id
            group = grouped.setdefault(
                sandbox_id,
                {
                    "sandbox_id": sandbox_id,
                    "provider_name": str(row.get("provider_name") or "local"),
                    "recipe_id": str(row.get("recipe_id") or "") or None,
                    "recipe": row.get("recipe_json"),
                    "observed_state": row.get("observed_state"),
                    "desired_state": row.get("desired_state"),
                    "created_at": row.get("created_at"),
                    "cwd": row.get("cwd"),
                    "_visible_threads": [],
                },
            )
            if include_runtime_session_id and runtime_session_id and not group.get("runtime_session_id"):
                group["runtime_session_id"] = runtime_session_id
            thread_id = str(row.get("thread_id") or "").strip()
            if not _is_user_visible_sandbox_thread(thread_id):
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
            group["_visible_threads"].append({"id": thread_id, **thread})
            if not group["cwd"] and row.get("cwd"):
                group["cwd"] = row.get("cwd")

        sandbox_rows: list[dict[str, Any]] = []
        for sandbox_row in grouped.values():
            visible_threads = canonical_owner_threads(sandbox_row.pop("_visible_threads"))
            if not visible_threads:
                continue
            if not _is_user_visible_sandbox_state(sandbox_row):
                continue
            thread_ids: list[str] = []
            agents: list[dict[str, Any]] = []
            for thread in visible_threads:
                thread_id = str(thread.get("id") or "").strip()
                agent_user_id = str(thread.get("agent_user_id") or "").strip()
                agent_user = users_by_id.get(agent_user_id)
                if not thread_id or not agent_user_id or agent_user is None:
                    continue
                thread_ids.append(thread_id)
                agents.append(_sandbox_agent_payload(thread_id, agent_user_id, agent_user))
            if not thread_ids:
                continue
            sandbox_row["thread_ids"] = thread_ids
            sandbox_row["agents"] = agents
            provider_name = sandbox_row["provider_name"]
            _apply_sandbox_recipe(sandbox_row, provider_name, sandbox_row["recipe"])
            sandbox_rows.append(sandbox_row)
        return sandbox_rows
    finally:
        monitor_repo.close()


def _sandbox_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "lease_id"}


def list_user_sandboxes(
    user_id: str,
    *,
    thread_repo: Any = None,
    user_repo: Any = None,
) -> list[dict[str, Any]]:
    rows = _list_user_runtime_rows(user_id, thread_repo=thread_repo, user_repo=user_repo)
    return [_sandbox_summary(row) for row in rows]


def count_user_visible_sandboxes_by_provider(
    user_id: str,
    *,
    thread_repo: Any = None,
    supabase_client: Any | None = None,
) -> dict[str, int]:
    if thread_repo is None:
        raise RuntimeError("thread_repo is required for count_user_visible_sandboxes_by_provider")
    repo_kwargs = {"supabase_client": supabase_client} if supabase_client is not None else {}
    monitor_repo = make_sandbox_monitor_repo(**repo_kwargs)
    try:
        owned_thread_ids = {
            str(thread.get("id") or "").strip()
            for thread in thread_repo.list_by_owner_user_id(user_id)
            if str(thread.get("id") or "").strip()
        }
        counts: Counter[str] = Counter()
        counted_sandbox_keys: set[str] = set()
        for row in monitor_repo.query_sandboxes():
            sandbox_id = str(row.get("sandbox_id") or "").strip()
            if not sandbox_id or sandbox_id in counted_sandbox_keys:
                continue
            thread_id = str(row.get("thread_id") or "").strip()
            if not _is_user_visible_sandbox_thread(thread_id) or thread_id not in owned_thread_ids:
                continue
            if not _is_user_visible_sandbox_state(row):
                continue
            counts[str(row.get("provider_name") or "local")] += 1
            counted_sandbox_keys.add(sandbox_id)
        return dict(counts)
    finally:
        monitor_repo.close()


def _is_user_visible_sandbox_thread(thread_id: str | None) -> bool:
    raw = str(thread_id or "").strip()
    return bool(raw) and not raw.startswith("subagent-") and not is_virtual_thread_id(raw)


def _is_user_visible_sandbox_state(sandbox_row: dict[str, Any]) -> bool:
    # @@@user-visible-sandbox-scope - product-facing sandbox summaries should only
    # expose sandboxes the user can still act on, not historical stopped/destroying
    # residue from monitor storage.
    status = map_sandbox_state_to_display_status(sandbox_row.get("observed_state"), sandbox_row.get("desired_state"))
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
            types.append(
                {
                    "name": name,
                    "provider": config.provider,
                    "available": True,
                    "capability": _capability_to_dict(provider_obj.get_capability()),
                }
            )
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

                key = _configured_api_key(name, config.agentbay.api_key, "AGENTBAY_API_KEY")
                if not key:
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

                key = _configured_api_key(name, config.e2b.api_key, "E2B_API_KEY")
                if not key:
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

                key = _configured_api_key(name, config.daytona.api_key, "DAYTONA_API_KEY")
                if not key:
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


def load_provider_orphan_sessions(managers: dict) -> list[dict]:
    """Load provider-visible runtimes that are not backed by a known managed runtime row."""
    sessions: list[dict] = []
    for provider_name, manager in managers.items():
        provider = getattr(manager, "provider", None)
        list_provider_runtimes = getattr(provider, "list_provider_runtimes", None)
        if not callable(list_provider_runtimes):
            continue
        provider_slug = getattr(provider, "name", provider_name)

        seen_instance_ids = {
            str(row.get("current_instance_id") or "").strip()
            for row in manager.lease_store.list_by_provider(provider_slug)
            if str(row.get("current_instance_id") or "").strip()
        }
        raw_provider_runtimes = list_provider_runtimes()
        if not isinstance(raw_provider_runtimes, list):
            raise TypeError(f"{provider_slug}.list_provider_runtimes must return list")
        provider_runtimes = raw_provider_runtimes

        inspect_visible = manager.provider_capability.inspect_visible
        for ps in provider_runtimes:
            instance_id = getattr(ps, "session_id", None)
            status = getattr(ps, "status", None) or "unknown"
            if not instance_id or status in {"deleted", "dead", "stopped"} or instance_id in seen_instance_ids:
                continue
            sessions.append(
                {
                    "session_id": instance_id,
                    "thread_id": "(orphan)",
                    "provider": provider_slug,
                    "status": status,
                    "created_at": None,
                    "last_active": None,
                    "lease_id": None,
                    "instance_id": instance_id,
                    "chat_session_id": None,
                    "source": "provider_orphan",
                    "inspect_visible": inspect_visible,
                }
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

    if thread_id and not is_virtual_thread_id(thread_id):
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
            mode = "provider_orphan_direct"
            if action == "pause":
                ok = manager.provider.pause_session(target_session_id)
            elif action == "resume":
                ok = manager.provider.resume_session(target_session_id)
            elif action == "destroy":
                ok = manager.provider.destroy_session(target_session_id)
            else:
                raise RuntimeError(f"Unknown action: {action}")
        else:
            mode = "manager_runtime"
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


def destroy_sandbox_runtime(*, lower_runtime_handle: str, provider_name: str, detach_thread_bindings: bool = False) -> dict[str, Any]:
    """Destroy lower sandbox runtime resources through the manager state machine."""
    _, managers = init_providers_and_managers()
    manager = managers.get(provider_name)
    if manager is None:
        raise RuntimeError(f"Provider manager unavailable: {provider_name}")

    lease = manager.get_lease(lower_runtime_handle)
    if lease is None:
        raise RuntimeError(f"Lower runtime not found: {lower_runtime_handle}")

    # @@@runtime-destroy-seam - detached residue may have no visible live session,
    # so cleanup must target the lower runtime handle directly rather than session lookup.
    _prune_stale_runtime_terminals(manager, lower_runtime_handle)
    if detach_thread_bindings:
        _detach_runtime_terminals(manager, lower_runtime_handle)
    if not manager.destroy_lease_resources(lower_runtime_handle):
        raise RuntimeError(f"Lower runtime not found: {lower_runtime_handle}")
    return {
        "ok": True,
        "action": "destroy",
        "lower_runtime_handle": lower_runtime_handle,
        "provider": provider_name,
        "mode": "manager_runtime",
    }


def _detach_runtime_terminals(manager: Any, lower_runtime_handle: str) -> None:
    for row in list(manager.terminal_store.list_all()):
        if str(row.get("lease_id") or "") != lower_runtime_handle:
            continue
        thread_id = str(row.get("thread_id") or "").strip()
        terminal_id = str(row.get("terminal_id") or "").strip()
        if not terminal_id:
            raise RuntimeError(f"Lower runtime {lower_runtime_handle} has terminal row without terminal_id")
        if thread_id:
            manager.session_manager.delete_thread(thread_id, reason="detached_sandbox_cleanup")
        manager.terminal_store.delete(terminal_id)


def _prune_stale_runtime_terminals(manager: Any, lower_runtime_handle: str) -> None:
    thread_repo = build_storage_container().thread_repo()
    try:
        for row in list(manager.terminal_store.list_all()):
            if str(row.get("lease_id") or "") != lower_runtime_handle:
                continue
            thread_id = str(row.get("thread_id") or "").strip()
            if thread_id and not is_virtual_thread_id(thread_id) and thread_repo.get_by_id(thread_id) is not None:
                continue
            terminal_id = str(row.get("terminal_id") or "").strip()
            if not terminal_id:
                raise RuntimeError(f"Lower runtime {lower_runtime_handle} has terminal row without terminal_id")
            # @@@runtime-cleanup-stale-terminal-prune - detached residue can keep dead terminal
            # pointers long after the owning thread row is gone; drop only those stale pointers
            # before enforcing the remaining bound-terminal guard.
            if thread_id and not is_virtual_thread_id(thread_id):
                manager.session_manager.delete_thread(thread_id, reason="stale_terminal_pruned")
            manager.terminal_store.delete(terminal_id)
    finally:
        thread_repo.close()


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
