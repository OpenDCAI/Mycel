from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from backend.bootstrap.app_entrypoint import add_permissive_cors
from backend.web.core.lifespan import lifespan
from backend.web.core.runtime_profile import RuntimeProfile, resolve_runtime_profile


def create_app(
    *,
    profile: RuntimeProfile | str | None = None,
    lifespan_context: Callable[[FastAPI], Any] | None = lifespan,
) -> FastAPI:
    runtime_profile = profile if isinstance(profile, RuntimeProfile) else resolve_runtime_profile(profile)
    app = FastAPI(title="Mycel Web Backend", lifespan=lifespan_context)
    app.state.runtime_profile = runtime_profile
    add_permissive_cors(app)
    if runtime_profile is RuntimeProfile.COMMUNICATION:
        include_communication_routes(app)
    else:
        include_full_routes(app)
    return app


def include_communication_routes(app: FastAPI) -> None:
    from backend.chat.api.http import app_router as chat_app_router
    from backend.web.routers import auth, contacts, users

    app.include_router(auth.router)
    app.include_router(chat_app_router.router)
    app.include_router(contacts.router)
    app.include_router(users.users_router)


def include_full_routes(app: FastAPI) -> None:
    from backend.chat.api.http import app_router as chat_app_router
    from backend.monitor.api.http import global_router
    from backend.web.routers import (
        auth,
        contacts,
        invite_codes,
        marketplace,
        monitor_threads,
        panel,
        resources,
        sandbox,
        settings,
        thread_files,
        threads,
        users,
        webhooks,
    )

    app.include_router(auth.router)
    app.include_router(invite_codes.router)
    app.include_router(threads.router)
    app.include_router(chat_app_router.router)
    app.include_router(contacts.router)
    app.include_router(users.users_router)
    app.include_router(sandbox.router)
    app.include_router(webhooks.router)
    app.include_router(thread_files.router)
    app.include_router(thread_files._public)
    app.include_router(settings.router)
    app.include_router(panel.router)
    app.include_router(global_router.router, prefix="/api/monitor")
    app.include_router(monitor_threads.router, prefix="/api/monitor")
    app.include_router(resources.router)
    app.include_router(marketplace.router)
