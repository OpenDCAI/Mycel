"""Separate-process Monitor app shell."""

from fastapi import FastAPI

from backend.bootstrap.app_entrypoint import add_permissive_cors, load_env_file_from_env, resolve_app_port, run_reloadable_app
from backend.monitor.api.http import global_router
from backend.monitor_app.lifespan import lifespan

load_env_file_from_env()

app = FastAPI(title="Leon Monitor Backend", lifespan=lifespan)
add_permissive_cors(app)

# @@@monitor-app-global-only - the first separate-process shell mounts only the route bucket already ruled process-safe.
app.include_router(global_router.router, prefix="/api/monitor")


def _resolve_port() -> int:
    return resolve_app_port("LEON_MONITOR_BACKEND_PORT", "worktree.ports.monitor-backend", 8011)


if __name__ == "__main__":
    run_reloadable_app(
        "backend.monitor_app.main:app",
        port=_resolve_port(),
        reload_dirs=["backend", "storage", "eval"],
    )
