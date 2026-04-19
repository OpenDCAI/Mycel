"""Separate-process Monitor app shell."""

from fastapi import FastAPI

from backend.monitor.api.http import global_router
from backend.monitor_app.lifespan import lifespan

app = FastAPI(title="Leon Monitor Backend", lifespan=lifespan)

# @@@monitor-app-global-only - the first separate-process shell mounts only the route bucket already ruled process-safe.
app.include_router(global_router.router, prefix="/api/monitor")
