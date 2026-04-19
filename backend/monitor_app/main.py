"""Separate-process Monitor app shell."""

import os
import subprocess

import uvicorn
from fastapi import FastAPI

from backend.monitor.api.http import global_router
from backend.monitor_app.lifespan import lifespan

app = FastAPI(title="Leon Monitor Backend", lifespan=lifespan)

# @@@monitor-app-global-only - the first separate-process shell mounts only the route bucket already ruled process-safe.
app.include_router(global_router.router, prefix="/api/monitor")


def _resolve_port() -> int:
    port = os.environ.get("LEON_MONITOR_BACKEND_PORT") or os.environ.get("PORT")
    if port:
        return int(port)
    try:
        result = subprocess.run(
            ["git", "config", "--worktree", "--get", "worktree.ports.monitor-backend"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return 8011


if __name__ == "__main__":
    uvicorn.run(
        "backend.monitor_app.main:app",
        host="0.0.0.0",
        port=_resolve_port(),
        reload=True,
        reload_dirs=["backend", "storage", "eval"],
    )
