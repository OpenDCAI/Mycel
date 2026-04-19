"""Separate-process Monitor app shell."""

import uvicorn
from fastapi import FastAPI

from backend.app_entrypoint import load_env_file_from_env, resolve_app_port
from backend.monitor.api.http import global_router
from backend.monitor_app.lifespan import lifespan

load_env_file_from_env()

app = FastAPI(title="Leon Monitor Backend", lifespan=lifespan)

# @@@monitor-app-global-only - the first separate-process shell mounts only the route bucket already ruled process-safe.
app.include_router(global_router.router, prefix="/api/monitor")


def _resolve_port() -> int:
    return resolve_app_port("LEON_MONITOR_BACKEND_PORT", "worktree.ports.monitor-backend", 8011)


if __name__ == "__main__":
    uvicorn.run(
        "backend.monitor_app.main:app",
        host="0.0.0.0",
        port=_resolve_port(),
        reload=True,
        reload_dirs=["backend", "storage", "eval"],
    )
