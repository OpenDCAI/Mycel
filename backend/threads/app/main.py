"""Separate-process Threads app shell."""

from fastapi import FastAPI

from backend.bootstrap.app_entrypoint import add_permissive_cors, load_env_file_from_env, resolve_app_port, run_reloadable_app
from backend.threads.api.http import app_router
from backend.threads.app.lifespan import lifespan

load_env_file_from_env()

app = FastAPI(title="Mycel Threads Backend", lifespan=lifespan)
add_permissive_cors(app)
app.include_router(app_router.router)


def _resolve_port() -> int:
    return resolve_app_port("LEON_THREADS_BACKEND_PORT", "worktree.ports.threads-backend", 8012)


if __name__ == "__main__":
    run_reloadable_app(
        "backend.threads.app.main:app",
        port=_resolve_port(),
        reload_dirs=["backend", "core", "storage", "sandbox", "messaging"],
    )
