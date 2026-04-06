"""Leon Web Backend - FastAPI Application."""

import os
import subprocess

# Load .env file if ENV_FILE is specified (e.g. ENV_FILE=.env for local dev)
_env_file = os.getenv("ENV_FILE")
if _env_file:
    from dotenv import load_dotenv

    load_dotenv(_env_file, override=False)

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend.web.core.lifespan import lifespan  # noqa: E402
from backend.web.routers import (  # noqa: E402
    auth,
    contacts,
    entities,
    invite_codes,
    marketplace,
    monitor,
    panel,
    sandbox,
    settings,
    thread_files,
    threads,
    webhooks,
)
from backend.web.routers import messaging as messaging_router  # noqa: E402
from messaging.relationships.router import router as relationships_router  # noqa: E402

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
app.include_router(auth.router)
app.include_router(invite_codes.router)
app.include_router(threads.router)

app.include_router(messaging_router.router)

app.include_router(contacts.router)
app.include_router(relationships_router)
app.include_router(entities.router)
app.include_router(entities.members_router)
app.include_router(sandbox.router)
app.include_router(webhooks.router)
app.include_router(thread_files.router)
app.include_router(thread_files._public)
app.include_router(settings.router)
app.include_router(panel.router)
app.include_router(monitor.router)
app.include_router(marketplace.router)


def _resolve_port() -> int:
    """Resolve backend port: env var > git worktree config > default 8001."""
    port = os.environ.get("LEON_BACKEND_PORT") or os.environ.get("PORT")
    if port:
        return int(port)
    try:
        result = subprocess.run(
            ["git", "config", "--worktree", "--get", "worktree.ports.backend"],
            capture_output=True,
            text=True,
            timeout=3,
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
    # @@@reload-dirs - restrict file watching to backend + core + config + storage only.
    # Without this, StatReload scans .venv/, node_modules/, .git/ etc. and burns 50-80% CPU.
    uvicorn.run(
        "backend.web.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_dirs=["backend", "core", "config", "storage", "sandbox", "messaging"],
    )
