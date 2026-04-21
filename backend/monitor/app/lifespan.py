"""Minimal lifespan for the separate Monitor app shell."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.bootstrap.storage import attach_runtime_storage_state
from backend.identity.auth.runtime_bootstrap import attach_auth_runtime_state
from backend.monitor.infrastructure.resources.resource_overview_cache import resource_overview_refresh_loop


def _require_monitor_runtime_contract(app: FastAPI) -> None:
    runtime_storage = attach_runtime_storage_state(app)
    app.state.user_repo = runtime_storage.storage_container.user_repo()
    attach_auth_runtime_state(
        app,
        storage_state=runtime_storage,
        contact_repo=runtime_storage.storage_container.contact_repo(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _require_monitor_runtime_contract(app)
    app.state.monitor_resources_task = None
    try:
        app.state.monitor_resources_task = asyncio.create_task(resource_overview_refresh_loop())
        yield
    finally:
        task = getattr(app.state, "monitor_resources_task", None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
