"""Separate-process Chat app shell."""

from fastapi import FastAPI

from backend.bootstrap.app_entrypoint import add_permissive_cors, load_env_file_from_env, resolve_app_port, run_reloadable_app
from backend.chat.api.http import app_router
from backend.chat.app.lifespan import lifespan

load_env_file_from_env()

app = FastAPI(title="Mycel Chat Backend", lifespan=lifespan)
add_permissive_cors(app)
app.include_router(app_router.router)


def _resolve_port() -> int:
    return resolve_app_port("LEON_CHAT_BACKEND_PORT", "worktree.ports.chat-backend", 8013)


if __name__ == "__main__":
    run_reloadable_app(
        "backend.chat.app.main:app",
        port=_resolve_port(),
        reload_dirs=["backend", "storage", "messaging"],
    )
