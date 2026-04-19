"""Sandbox management service."""

import json
import logging
import os
from collections import Counter
from datetime import datetime
from typing import Any

import backend.user_sandbox_reads as user_sandbox_reads
from backend import sandbox_inventory
from backend import sandbox_provider_factory as _sandbox_provider_factory
from backend import sandbox_runtime_mutations as _sandbox_runtime_mutations
from backend.web.core.config import LOCAL_WORKSPACE_ROOT, SANDBOXES_DIR
from backend.web.services.thread_visibility import canonical_owner_threads
from backend.web.utils.helpers import is_virtual_thread_id
from backend.web.utils.serializers import avatar_url
from sandbox.config import SandboxConfig
from sandbox.manager import SandboxManager
from sandbox.recipes import default_recipe_id, list_builtin_recipes, normalize_recipe_snapshot, provider_type_from_name
from storage.models import map_sandbox_state_to_display_status
from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo
from storage.runtime import build_storage_container

logger = logging.getLogger(__name__)


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
    return user_sandbox_reads._list_user_runtime_rows(
        user_id,
        thread_repo=thread_repo,
        user_repo=user_repo,
        include_runtime_session_id=include_runtime_session_id,
        make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
        canonical_owner_threads_fn=canonical_owner_threads,
        avatar_url_fn=avatar_url,
        is_virtual_thread_id_fn=is_virtual_thread_id,
    )


def _sandbox_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "lease_id"}


def list_user_sandboxes(
    user_id: str,
    *,
    thread_repo: Any = None,
    user_repo: Any = None,
) -> list[dict[str, Any]]:
    return user_sandbox_reads.list_user_sandboxes(
        user_id,
        thread_repo=thread_repo,
        user_repo=user_repo,
        make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
        canonical_owner_threads_fn=canonical_owner_threads,
        avatar_url_fn=avatar_url,
        is_virtual_thread_id_fn=is_virtual_thread_id,
    )


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
    return sandbox_inventory.available_sandbox_types(
        sandboxes_dir=SANDBOXES_DIR,
        init_providers_and_managers_fn=init_providers_and_managers,
        sandbox_config_cls=SandboxConfig,
    )


def init_providers_and_managers() -> tuple[dict, dict]:
    return sandbox_inventory.init_providers_and_managers()


def _build_providers_and_managers() -> tuple[dict[str, Any], dict[str, Any]]:
    return sandbox_inventory._build_providers_and_managers(
        sandboxes_dir=SANDBOXES_DIR,
        sandbox_manager_cls=SandboxManager,
        sandbox_config_cls=SandboxConfig,
        local_workspace_root_path=LOCAL_WORKSPACE_ROOT,
    )


def load_all_sandbox_runtimes(managers: dict) -> list[dict]:
    """Load sandbox runtime rows from all managers in parallel."""
    runtimes: list[dict] = []
    if not managers:
        return runtimes
    for provider_name, manager in managers.items():
        rows = manager.list_sessions()
        for row in rows:
            runtimes.append(
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

    # @@@stable-runtime-order - Keep deterministic ordering across refreshes/providers.
    def _to_ts(value: Any) -> float:
        if not value or not isinstance(value, str):
            return 0.0
        try:
            return datetime.fromisoformat(value).timestamp()
        except Exception:
            return 0.0

    runtimes.sort(
        key=lambda row: (
            -_to_ts(row.get("created_at")),
            -_to_ts(row.get("last_active")),
            str(row.get("provider") or ""),
            str(row.get("thread_id") or ""),
            str(row.get("session_id") or ""),
        )
    )
    return runtimes


def load_provider_orphan_runtimes(managers: dict) -> list[dict]:
    return sandbox_inventory.load_provider_orphan_runtimes(managers)


def list_provider_orphan_runtimes() -> list[dict]:
    return sandbox_inventory.list_provider_orphan_runtimes(init_providers_and_managers_fn=init_providers_and_managers)


def find_runtime_and_manager(
    runtimes: list[dict],
    managers: dict,
    runtime_id: str,
    provider_name: str | None = None,
) -> tuple[dict | None, Any | None]:
    """Find sandbox runtime by external ID/prefix (+optional provider), return (runtime, manager)."""
    candidates: list[dict] = []
    for runtime in runtimes:
        if provider_name and runtime.get("provider") != provider_name:
            continue
        sid = str(runtime.get("session_id") or "")
        if sid == runtime_id or sid.startswith(runtime_id):
            candidates.append(runtime)
    if not candidates:
        return None, None
    if len(candidates) == 1:
        chosen = candidates[0]
        return chosen, managers.get(chosen["provider"])
    exact = [runtime for runtime in candidates if str(runtime.get("session_id") or "") == runtime_id]
    if len(exact) == 1:
        chosen = exact[0]
        return chosen, managers.get(chosen["provider"])
    raise RuntimeError(f"Ambiguous runtime id '{runtime_id}'. Specify provider query param.")


def mutate_sandbox_runtime(
    *,
    runtime_id: str,
    action: str,
    provider_hint: str | None = None,
) -> dict[str, Any]:
    return _sandbox_runtime_mutations.mutate_sandbox_runtime(
        runtime_id=runtime_id,
        action=action,
        provider_hint=provider_hint,
        init_providers_and_managers_fn=init_providers_and_managers,
        load_all_sandbox_runtimes_fn=load_all_sandbox_runtimes,
        find_runtime_and_manager_fn=find_runtime_and_manager,
    )


def destroy_sandbox_runtime(*, lower_runtime_handle: str, provider_name: str, detach_thread_bindings: bool = False) -> dict[str, Any]:
    return _sandbox_runtime_mutations.destroy_sandbox_runtime(
        lower_runtime_handle=lower_runtime_handle,
        provider_name=provider_name,
        detach_thread_bindings=detach_thread_bindings,
        init_providers_and_managers_fn=init_providers_and_managers,
        build_storage_container_fn=build_storage_container,
    )


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


def get_runtime_metrics(runtime_id: str, provider_hint: str | None = None) -> dict[str, Any]:
    """Load one sandbox runtime's provider metrics through the current manager inventory."""
    _, managers = init_providers_and_managers()
    runtimes = load_all_sandbox_runtimes(managers)
    runtime, manager = find_runtime_and_manager(runtimes, managers, runtime_id, provider_name=provider_hint)
    if not runtime:
        raise RuntimeError(f"Runtime not found: {runtime_id}")
    if manager is None:
        raise RuntimeError(f"Provider manager unavailable: {runtime.get('provider')}")

    target_runtime_id = str(runtime.get("instance_id") or runtime.get("session_id") or runtime_id)
    metrics = manager.provider.get_metrics(target_runtime_id)
    if metrics is None:
        return {"session_id": target_runtime_id, "provider": runtime.get("provider"), "metrics": None}
    return {
        "session_id": target_runtime_id,
        "provider": runtime.get("provider"),
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


build_provider_from_config_name = _sandbox_provider_factory.build_provider_from_config_name


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
