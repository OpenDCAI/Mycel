"""Minimal lifespan for the separate Monitor app shell."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.bootstrap.storage import attach_runtime_storage_state
from backend.monitor.infrastructure.resources.resource_overview_cache import resource_overview_refresh_loop


def _require_monitor_runtime_contract(app: FastAPI) -> None:
    attach_runtime_storage_state(app)


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
