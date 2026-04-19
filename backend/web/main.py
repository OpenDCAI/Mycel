"""Leon Web Backend - FastAPI Application."""

from backend.app_entrypoint import load_env_file_from_env, resolve_app_port

load_env_file_from_env()

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend.chat.api.http import (  # noqa: E402
    conversations_router,  # noqa: E402
    relationships_router,  # noqa: E402
)
from backend.chat.api.http import router as messaging_router  # noqa: E402
from backend.monitor.api.http import router as monitor_router  # noqa: E402
from backend.web.core.lifespan import lifespan  # noqa: E402
from backend.web.routers import (  # noqa: E402
    auth,
    contacts,
    invite_codes,
    marketplace,
    panel,
    resources,
    sandbox,
    settings,
    thread_files,
    threads,
    users,
    webhooks,
)

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
app.include_router(relationships_router.router)
app.include_router(users.users_router)
app.include_router(sandbox.router)
app.include_router(webhooks.router)
app.include_router(thread_files.router)
app.include_router(thread_files._public)
app.include_router(settings.router)
app.include_router(panel.router)
app.include_router(monitor_router.router)
app.include_router(resources.router)
app.include_router(marketplace.router)
app.include_router(conversations_router.router)


def _resolve_port() -> int:
    """Resolve backend port: env var > git worktree config > default 8001."""
    return resolve_app_port("LEON_BACKEND_PORT", "worktree.ports.backend", 8001)


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
