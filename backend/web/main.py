"""Leon Web Backend - FastAPI Application."""

import os
import subprocess

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.web.core.lifespan import lifespan
from backend.web.monitor import router as monitor_router
from backend.web.routers import debug, panel, sandbox, settings, threads, webhooks, workspace

# Create FastAPI app
app = FastAPI(title="Leon Web Backend", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(threads.router)
app.include_router(sandbox.router)
app.include_router(webhooks.router)
app.include_router(workspace.router)
app.include_router(settings.router)
app.include_router(debug.router)
app.include_router(panel.router)
app.include_router(monitor_router)


def _resolve_port() -> int:
    """Resolve backend port: env var > git worktree config > default 8001."""
    port = os.environ.get("LEON_BACKEND_PORT") or os.environ.get("PORT")
    if port:
        return int(port)
    try:
        result = subprocess.run(
            ["git", "config", "--worktree", "--get", "worktree.ports.backend"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return 8001


if __name__ == "__main__":
    # @@@port-precedence - git worktree config > LEON_BACKEND_PORT > PORT > 8001
    port = _resolve_port()
    # @@@module-launch-target - Package-qualified target keeps module launch (`python -m backend.web.main`) import-safe.
    uvicorn.run("backend.web.main:app", host="0.0.0.0", port=port, reload=True)
