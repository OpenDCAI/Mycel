"""Shared sandbox thread resource cleanup helpers."""

from __future__ import annotations

from backend.sandbox_inventory import init_providers_and_managers


def destroy_thread_resources_sync(
    thread_id: str,
    sandbox_type: str,
    agent_pool: dict,
    *,
    init_providers_and_managers_fn=init_providers_and_managers,
) -> bool:
    pool_key = f"{thread_id}:{sandbox_type}"
    pooled_agent = agent_pool.get(pool_key)
    if pooled_agent and hasattr(pooled_agent, "_sandbox"):
        manager = pooled_agent._sandbox.manager
    else:
        _, managers = init_providers_and_managers_fn()
        manager = managers.get(sandbox_type)
    if not manager:
        raise RuntimeError(f"No sandbox manager found for provider {sandbox_type}")
    return manager.destroy_thread_resources(thread_id)
