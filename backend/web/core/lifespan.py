"""Application lifespan management."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg import AsyncConnection

from backend.threads.pool import idle_reaper as idle_reaper_owner


def _require_web_runtime_contract() -> None:
    # @@@web-checkpointer-contract - web routes can create LeonAgent on first
    # message, so missing Postgres checkpointer config is a startup contract
    # violation, not a late per-request error.
    if not os.getenv("LEON_POSTGRES_URL"):
        raise RuntimeError("LEON_POSTGRES_URL is required for backend web runtime")


async def _validate_web_checkpointer_contract() -> None:
    pg_url = os.getenv("LEON_POSTGRES_URL")
    if not pg_url:
        raise RuntimeError("LEON_POSTGRES_URL is required for backend web runtime")

    conn = await AsyncConnection.connect(pg_url)
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT 1")
            await cursor.fetchone()
    finally:
        await conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    _require_web_runtime_contract()
    await _validate_web_checkpointer_contract()

    # ---- Chat repos + services ----
    from backend.bootstrap.storage import attach_runtime_storage_state
    from backend.identity.auth.runtime_bootstrap import attach_auth_runtime_state

    runtime_storage = attach_runtime_storage_state(app)
    _supabase_client = runtime_storage.supabase_client
    storage_container = runtime_storage.storage_container
    from core.runtime.langgraph_checkpoint_store import LangGraphCheckpointStore, agent_checkpoint_saver_from_conn_string

    pg_url = os.environ["LEON_POSTGRES_URL"]
    app.state._thread_checkpoint_saver_ctx = agent_checkpoint_saver_from_conn_string(pg_url)
    app.state._thread_checkpoint_saver = await app.state._thread_checkpoint_saver_ctx.__aenter__()
    await app.state._thread_checkpoint_saver.setup()
    app.state.thread_checkpoint_store = LangGraphCheckpointStore(app.state._thread_checkpoint_saver)

    app.state.user_repo = storage_container.user_repo()
    app.state.thread_repo = storage_container.thread_repo()
    app.state.lease_repo = storage_container.lease_repo()
    app.state.recipe_repo = storage_container.recipe_repo()
    app.state.workspace_repo = storage_container.workspace_repo()
    app.state.sandbox_repo = storage_container.sandbox_repo()
    app.state.invite_code_repo = storage_container.invite_code_repo()
    app.state.user_settings_repo = storage_container.user_settings_repo()
    app.state.agent_config_repo = storage_container.agent_config_repo()
    attach_auth_runtime_state(app, storage_state=runtime_storage, contact_repo=storage_container.contact_repo())

    from backend.chat.bootstrap import attach_chat_runtime, wire_chat_delivery
    from backend.threads.bootstrap import attach_threads_runtime

    # @@@web-chat-before-threads - threads bootstrap now constructs the agent
    # runtime gateway eagerly, and that path requires chat-owned typing state
    # to exist first. Reordering this back will fail startup on fresh dev.
    chat_runtime = attach_chat_runtime(
        app,
        storage_container,
        user_repo=app.state.user_repo,
        thread_repo=app.state.thread_repo,
    )
    attach_threads_runtime(app, storage_container, typing_tracker=chat_runtime.typing_tracker)
    wire_chat_delivery(
        app,
        messaging_service=chat_runtime.messaging_service,
        activity_reader=app.state.agent_runtime_thread_activity_reader,
        thread_repo=app.state.thread_repo,
    )

    # ---- Existing state ----
    from backend.threads.display.builder import DisplayBuilder

    app.state.display_builder = DisplayBuilder()
    app.state.idle_reaper_task = None
    app.state._event_loop = asyncio.get_running_loop()

    try:
        from backend.sandboxes.service import init_providers_and_managers
        from backend.web.core.config import IDLE_REAPER_INTERVAL_SEC

        idle_reaper_owner.init_providers_and_managers = init_providers_and_managers
        idle_reaper_owner.IDLE_REAPER_INTERVAL_SEC = IDLE_REAPER_INTERVAL_SEC

        # Start idle reaper background task
        app.state.idle_reaper_task = asyncio.create_task(idle_reaper_owner.idle_reaper_loop(app))

        yield
    finally:
        for task_name in ("idle_reaper_task",):
            task = getattr(app.state, task_name, None)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if hasattr(app.state, "recipe_repo"):
            app.state.recipe_repo.close()

        checkpoint_saver_ctx = getattr(app.state, "_thread_checkpoint_saver_ctx", None)
        if checkpoint_saver_ctx is not None:
            await checkpoint_saver_ctx.__aexit__(None, None, None)

        # Cleanup: close all agents
        for agent in app.state.agent_pool.values():
            try:
                agent.close(cleanup_sandbox=False)
            except Exception as e:
                print(f"[web] Agent cleanup error: {e}")

        # Cleanup: stop LSP language servers
        from core.tools.lsp.service import lsp_pool

        await lsp_pool.close_all()
