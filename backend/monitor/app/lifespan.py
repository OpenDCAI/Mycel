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
    monitor_resources_task = None
    try:
        monitor_resources_task = asyncio.create_task(resource_overview_refresh_loop())
        yield
    finally:
        if monitor_resources_task:
            monitor_resources_task.cancel()
            try:
                await monitor_resources_task
            except asyncio.CancelledError:
                pass
