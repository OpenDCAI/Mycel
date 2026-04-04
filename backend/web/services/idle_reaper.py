"""Idle session reaper service."""

import asyncio

from fastapi import FastAPI

from backend.web.core.config import IDLE_REAPER_INTERVAL_SEC

from .sandbox_service import init_providers_and_managers


def run_idle_reaper_once(app_obj: FastAPI) -> int:
    """External idle manager: enforce idle timeout across providers."""
    total = 0
    managed_providers: set[str] = set()

    # First use live managers from resident agents (can close live runtimes safely).
    for agent in app_obj.state.agent_pool.values():
        sandbox = getattr(agent, "_sandbox", None)
        manager = getattr(sandbox, "manager", None)
        if manager is None:
            continue
        provider_name = str(getattr(manager.provider, "name", ""))
        managed_providers.add(provider_name)
        total += manager.enforce_idle_timeouts()

    # Then cover providers without resident agent (DB-only cleanup).
    _, managers = init_providers_and_managers()
    for provider_name, manager in managers.items():
        if provider_name in managed_providers:
            continue
        total += manager.enforce_idle_timeouts()

    return total


async def idle_reaper_loop(app_obj: FastAPI) -> None:
    """Background task that periodically enforces idle timeouts."""
    while True:
        try:
            count = await asyncio.to_thread(run_idle_reaper_once, app_obj)
            if count > 0:
                print(f"[idle-reaper] reclaimed+closed {count} expired chat session(s)")
        except Exception as e:
            print(f"[idle-reaper] error: {e}")
        await asyncio.sleep(IDLE_REAPER_INTERVAL_SEC)
