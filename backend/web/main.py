"""Mycel Web Backend - FastAPI Application."""

from backend.bootstrap.app_entrypoint import add_permissive_cors, load_env_file_from_env, resolve_app_port, run_reloadable_app

load_env_file_from_env()

from fastapi import FastAPI  # noqa: E402

from backend.chat.api.http import app_router as chat_app_router  # noqa: E402
from backend.monitor.api.http import global_router  # noqa: E402
from backend.threads.api.http import app_router as threads_app_router  # noqa: E402
from backend.web.core.lifespan import lifespan  # noqa: E402
from backend.web.routers import (  # noqa: E402
    auth,
    invite_codes,
    marketplace,
    monitor_threads,
    panel,
    resources,
    sandbox,
    settings,
    users,
    webhooks,
)

# Create FastAPI app
app = FastAPI(title="Mycel Web Backend", lifespan=lifespan)

add_permissive_cors(app)

# Include routers
app.include_router(auth.router)
app.include_router(invite_codes.router)
app.include_router(chat_app_router.router)
app.include_router(threads_app_router.router)

app.include_router(users.users_router)
app.include_router(sandbox.router)
app.include_router(webhooks.router)
app.include_router(settings.router)
app.include_router(panel.router)
app.include_router(global_router.router, prefix="/api/monitor")
app.include_router(monitor_threads.router, prefix="/api/monitor")
app.include_router(resources.router)
app.include_router(marketplace.router)


def _resolve_port() -> int:
    """Resolve backend port: env var > git worktree config > default 8001."""
    return resolve_app_port("LEON_BACKEND_PORT", "worktree.ports.backend", 8001)


if __name__ == "__main__":
    # @@@port-precedence - git worktree config > LEON_BACKEND_PORT > PORT > 8001
    port = _resolve_port()
    # @@@module-launch-target - Package-qualified target keeps module launch (`python -m backend.web.main`) import-safe.
    # @@@reload-dirs - restrict file watching to backend + core + config + storage only.
    # Without this, StatReload scans .venv/, node_modules/, .git/ etc. and burns 50-80% CPU.
    run_reloadable_app(
        "backend.web.main:app",
        port=port,
        reload_dirs=["backend", "core", "config", "storage", "sandbox", "messaging"],
    )
