"""Application lifespan management."""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI
from psycopg import AsyncConnection

from backend.web.services.event_buffer import RunEventBuffer, ThreadEventBuffer
from backend.web.services.idle_reaper import idle_reaper_loop
from backend.web.services.resource_cache import monitor_resource_overview_refresh_loop
from core.runtime.middleware.queue import MessageQueueManager


def _get_pg_url() -> str | None:
    # Accept both the new standard name and the legacy LEON_ name for backward
    # compatibility with environments not yet migrated (e.g. docker-compose.yaml).
    return os.getenv("DATABASE_URL") or os.getenv("LEON_POSTGRES_URL")


def _require_web_runtime_contract() -> None:
    # @@@web-checkpointer-contract - web routes can create LeonAgent on first
    # message, so missing Postgres checkpointer config is a startup contract
    # violation, not a late per-request error.
    if not _get_pg_url():
        raise RuntimeError("DATABASE_URL is required for backend web runtime")


async def _validate_web_checkpointer_contract() -> None:
    pg_url = _get_pg_url()
    if not pg_url:
        raise RuntimeError("DATABASE_URL is required for backend web runtime")

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

    # ---- Member-Chat repos + services ----
    from backend.web.core.supabase_factory import create_supabase_auth_client, create_supabase_client
    from storage.container import StorageContainer

    _supabase_client = create_supabase_client()
    storage_container = StorageContainer(supabase_client=_supabase_client)
    app.state.member_repo = storage_container.member_repo()
    app.state.thread_repo = storage_container.thread_repo()
    app.state.thread_launch_pref_repo = storage_container.thread_launch_pref_repo()
    app.state.recipe_repo = storage_container.recipe_repo()
    app.state.chat_repo = storage_container.chat_repo()
    app.state.invite_code_repo = storage_container.invite_code_repo()
    app.state.user_settings_repo = storage_container.user_settings_repo()
    app.state.agent_config_repo = storage_container.agent_config_repo()
    app.state.panel_task_repo = storage_container.panel_task_repo()
    app.state.cron_job_repo = storage_container.cron_job_repo()
    app.state._supabase_client = _supabase_client
    app.state._supabase_auth_client_factory = create_supabase_auth_client
    app.state._storage_container = storage_container

    from backend.web.services.auth_service import AuthService

    app.state.auth_service = AuthService(
        members=app.state.member_repo,
        supabase_client=_supabase_client,
        supabase_auth_client_factory=create_supabase_auth_client,
        invite_codes=app.state.invite_code_repo,
    )

    from backend.web.services.chat_events import ChatEventBus
    from backend.web.services.typing_tracker import TypingTracker

    app.state.chat_event_bus = ChatEventBus()
    app.state.typing_tracker = TypingTracker(app.state.chat_event_bus)

    app.state.contact_repo = storage_container.contact_repo()

    # Wire chat delivery after event loop is available
    # ---- Messaging system (Supabase-backed, required) ----
    from core.agents.communication.delivery import make_chat_delivery_fn
    from messaging.delivery.resolver import HireVisitDeliveryResolver
    from messaging.relationships.service import RelationshipService
    from messaging.service import MessagingService
    from storage.providers.supabase.messaging_repo import (
        SupabaseChatMemberRepo,
        SupabaseMessageReadRepo,
        SupabaseMessagesRepo,
        SupabaseRelationshipRepo,
    )

    _msg_supabase = _supabase_client
    _chat_member_repo = SupabaseChatMemberRepo(_msg_supabase)
    _messages_repo = SupabaseMessagesRepo(_msg_supabase)
    _message_read_repo = SupabaseMessageReadRepo(_msg_supabase)
    app.state.relationship_repo = SupabaseRelationshipRepo(_msg_supabase)
    app.state.chat_member_repo = _chat_member_repo
    app.state.messages_repo = _messages_repo

    app.state.relationship_service = RelationshipService(
        app.state.relationship_repo,
        member_repo=app.state.member_repo,
        thread_repo=app.state.thread_repo,
    )

    _msg_delivery_resolver = HireVisitDeliveryResolver(
        contact_repo=app.state.contact_repo,
        chat_member_repo=_chat_member_repo,
        relationship_repo=app.state.relationship_repo,
    )

    app.state.messaging_service = MessagingService(
        chat_repo=app.state.chat_repo,
        chat_member_repo=_chat_member_repo,
        messages_repo=_messages_repo,
        message_read_repo=_message_read_repo,
        member_repo=app.state.member_repo,
        thread_repo=app.state.thread_repo,
        event_bus=app.state.chat_event_bus,
        delivery_resolver=_msg_delivery_resolver,
    )
    app.state.messaging_service.set_delivery_fn(make_chat_delivery_fn(app))

    # ---- Existing state ----
    app.state.queue_manager = MessageQueueManager()
    app.state.agent_pool = cast(dict[str, Any], {})
    app.state.thread_sandbox = cast(dict[str, str], {})
    app.state.thread_cwd = cast(dict[str, str], {})
    app.state.thread_locks = cast(dict[str, asyncio.Lock], {})
    app.state.thread_locks_guard = asyncio.Lock()
    app.state.thread_tasks = cast(dict[str, asyncio.Task[Any]], {})
    app.state.thread_event_buffers = cast(dict[str, ThreadEventBuffer], {})
    app.state.subagent_buffers = cast(dict[str, RunEventBuffer], {})

    from backend.web.services.display_builder import DisplayBuilder

    app.state.display_builder = DisplayBuilder()
    app.state.thread_last_active = cast(dict[str, float], {})  # thread_id → epoch timestamp
    app.state.idle_reaper_task = cast(asyncio.Task[Any] | None, None)
    app.state.cron_service = None
    app.state._event_loop = asyncio.get_running_loop()
    app.state.monitor_resources_task = cast(asyncio.Task[Any] | None, None)

    try:
        # Start idle reaper background task
        app.state.idle_reaper_task = asyncio.create_task(idle_reaper_loop(app))

        # Start resource overview refresh loop
        app.state.monitor_resources_task = asyncio.create_task(monitor_resource_overview_refresh_loop())

        # Start cron scheduler
        from backend.web.services.cron_service import CronService

        cron_svc = CronService(
            cron_job_repo=app.state.cron_job_repo,
            task_repo=app.state.panel_task_repo,
        )
        await cron_svc.start()
        app.state.cron_service = cron_svc

        yield
    finally:
        # @@@background-task-shutdown-order - cancel monitor/reaper before provider cleanup.
        for task_name in ("monitor_resources_task", "idle_reaper_task"):
            task = getattr(app.state, task_name, None)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Cleanup: stop cron scheduler
        if app.state.cron_service:
            await app.state.cron_service.stop()

        if hasattr(app.state, "recipe_repo"):
            app.state.recipe_repo.close()

        # Cleanup: close all agents
        for agent in app.state.agent_pool.values():
            try:
                agent.close()
            except Exception as e:
                print(f"[web] Agent cleanup error: {e}")

        # Cleanup: stop LSP language servers
        from core.tools.lsp.service import lsp_pool

        await lsp_pool.close_all()
