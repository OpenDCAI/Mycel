"""Application lifespan management."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg import AsyncConnection

from backend.web.services.idle_reaper import idle_reaper_loop
from backend.web.services.resource_cache import resource_overview_refresh_loop
from core.runtime.middleware.queue import MessageQueueManager


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
    from backend.web.core.supabase_factory import create_public_supabase_client, create_supabase_auth_client, create_supabase_client
    from storage.runtime import build_storage_container

    _supabase_client = create_supabase_client()
    _public_supabase_client = create_public_supabase_client()
    storage_container = build_storage_container(
        supabase_client=_supabase_client,
        public_supabase_client=_public_supabase_client,
    )
    app.state.user_repo = storage_container.user_repo()
    app.state.thread_repo = storage_container.thread_repo()
    app.state.lease_repo = storage_container.lease_repo()
    app.state.terminal_repo = storage_container.terminal_repo()
    app.state.chat_session_repo = storage_container.chat_session_repo()
    app.state.sandbox_volume_repo = storage_container.sandbox_volume_repo()
    app.state.thread_launch_pref_repo = storage_container.thread_launch_pref_repo()
    app.state.recipe_repo = storage_container.recipe_repo()
    app.state.chat_repo = storage_container.chat_repo()
    app.state.invite_code_repo = storage_container.invite_code_repo()
    app.state.user_settings_repo = storage_container.user_settings_repo()
    app.state.agent_config_repo = storage_container.agent_config_repo()
    app.state.contact_repo = storage_container.contact_repo()
    app.state._supabase_client = _supabase_client
    app.state._public_supabase_client = _public_supabase_client
    app.state._supabase_auth_client_factory = create_supabase_auth_client
    app.state._storage_container = storage_container

    from backend.web.services.auth_service import AuthService

    app.state.auth_service = AuthService(
        users=app.state.user_repo,
        agent_configs=app.state.agent_config_repo,
        supabase_client=_supabase_client,
        supabase_auth_client_factory=create_supabase_auth_client,
        invite_codes=app.state.invite_code_repo,
        contact_repo=app.state.contact_repo,
    )

    from backend.web.services.chat_events import ChatEventBus
    from backend.web.services.typing_tracker import TypingTracker

    app.state.chat_event_bus = ChatEventBus()
    app.state.typing_tracker = TypingTracker(app.state.chat_event_bus)

    # Wire chat delivery after event loop is available
    # ---- Messaging system (Supabase-backed, required) ----
    from backend.web.core.supabase_factory import create_messaging_supabase_client
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

    _msg_supabase = create_messaging_supabase_client()
    _chat_member_repo = SupabaseChatMemberRepo(_msg_supabase)
    _messages_repo = SupabaseMessagesRepo(_msg_supabase)
    _message_read_repo = SupabaseMessageReadRepo(_msg_supabase)
    app.state.relationship_repo = SupabaseRelationshipRepo(_msg_supabase)
    app.state.chat_member_repo = _chat_member_repo
    app.state.messages_repo = _messages_repo

    app.state.relationship_service = RelationshipService(app.state.relationship_repo)

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
        user_repo=app.state.user_repo,
        thread_repo=app.state.thread_repo,
        event_bus=app.state.chat_event_bus,
        delivery_resolver=_msg_delivery_resolver,
    )
    app.state.messaging_service.set_delivery_fn(make_chat_delivery_fn(app))

    # ---- Existing state ----
    app.state.queue_manager = MessageQueueManager(repo=storage_container.queue_repo())
    app.state.agent_pool = {}
    app.state.thread_sandbox = {}
    app.state.thread_cwd = {}
    app.state.thread_locks = {}
    app.state.thread_locks_guard = asyncio.Lock()
    app.state.thread_tasks = {}
    app.state.thread_event_buffers = {}
    app.state.subagent_buffers = {}

    from backend.web.services.display_builder import DisplayBuilder

    app.state.display_builder = DisplayBuilder()
    app.state.thread_last_active = {}  # thread_id → epoch timestamp
    app.state.idle_reaper_task = None
    app.state._event_loop = asyncio.get_running_loop()
    app.state.monitor_resources_task = None

    try:
        # Start idle reaper background task
        app.state.idle_reaper_task = asyncio.create_task(idle_reaper_loop(app))

        # Start resource overview refresh loop
        app.state.monitor_resources_task = asyncio.create_task(resource_overview_refresh_loop())

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

        if hasattr(app.state, "recipe_repo"):
            app.state.recipe_repo.close()

        # Cleanup: close all agents
        for agent in app.state.agent_pool.values():
            try:
                agent.close(cleanup_sandbox=False)
            except Exception as e:
                print(f"[web] Agent cleanup error: {e}")

        # Cleanup: stop LSP language servers
        from core.tools.lsp.service import lsp_pool

        await lsp_pool.close_all()
