"""Shared sandbox runtime mutation helpers."""

from __future__ import annotations

from typing import Any

from backend.sandboxes.inventory import init_providers_and_managers
from backend.threads.virtual_threads import is_virtual_thread_id
from storage.runtime import build_storage_container


def mutate_sandbox_runtime(
    *,
    runtime_id: str,
    action: str,
    provider_hint: str | None = None,
    init_providers_and_managers_fn=init_providers_and_managers,
    load_all_sandbox_runtimes_fn,
    find_runtime_and_manager_fn,
) -> dict[str, Any]:
    _, managers = init_providers_and_managers_fn()
    runtimes = load_all_sandbox_runtimes_fn(managers)
    runtime, manager = find_runtime_and_manager_fn(runtimes, managers, runtime_id, provider_name=provider_hint)
    if not runtime:
        raise RuntimeError(f"Runtime not found: {runtime_id}")

    provider_name = str(runtime.get("provider") or "")
    if not manager:
        raise RuntimeError(f"Provider manager unavailable: {provider_name}")

    thread_id = str(runtime.get("thread_id") or "")
    lease_id = runtime.get("lease_id")
    target_runtime_id = str(runtime.get("session_id") or runtime_id)

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
                ok = manager.provider.pause_session(target_runtime_id)
            elif action == "resume":
                ok = manager.provider.resume_session(target_runtime_id)
            elif action == "destroy":
                ok = manager.provider.destroy_session(target_runtime_id)
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
        raise RuntimeError(f"Failed to {action} runtime {target_runtime_id}")

    return {
        "ok": True,
        "action": action,
        "session_id": target_runtime_id,
        "provider": provider_name,
        "thread_id": thread_id or None,
        "lease_id": lease_id,
        "mode": mode,
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


def _prune_stale_runtime_terminals(manager: Any, lower_runtime_handle: str, *, build_storage_container_fn=build_storage_container) -> None:
    thread_repo = build_storage_container_fn().thread_repo()
    try:
        for row in list(manager.terminal_store.list_all()):
            if str(row.get("lease_id") or "") != lower_runtime_handle:
                continue
            thread_id = str(row.get("thread_id") or "").strip()
            terminal_id = str(row.get("terminal_id") or "").strip()
            if not thread_id or not terminal_id:
                continue
            if thread_repo.get_by_id(thread_id) is not None:
                continue
            manager.session_manager.delete_thread(thread_id, reason="stale_terminal_pruned")
            manager.terminal_store.delete(terminal_id)
    finally:
        thread_repo.close()


def destroy_sandbox_runtime(
    *,
    lower_runtime_handle: str,
    provider_name: str,
    detach_thread_bindings: bool = False,
    init_providers_and_managers_fn=init_providers_and_managers,
    build_storage_container_fn=build_storage_container,
) -> dict[str, Any]:
    _, managers = init_providers_and_managers_fn()
    manager = managers.get(provider_name)
    if manager is None:
        raise RuntimeError(f"Provider manager unavailable: {provider_name}")

    lease = manager.get_lease(lower_runtime_handle)
    if lease is None:
        raise RuntimeError(f"Lower runtime not found: {lower_runtime_handle}")

    _prune_stale_runtime_terminals(manager, lower_runtime_handle, build_storage_container_fn=build_storage_container_fn)
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
