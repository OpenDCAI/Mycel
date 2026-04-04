"""Application lifespan management."""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from backend.web.services.event_buffer import RunEventBuffer, ThreadEventBuffer
from backend.web.services.idle_reaper import idle_reaper_loop
from backend.web.services.resource_cache import resource_overview_refresh_loop
from config.env_manager import ConfigManager
from core.runtime.middleware.queue import MessageQueueManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    # Load configuration
    config_manager = ConfigManager()
    config_manager.load_to_env()

    # Ensure event store table exists (lazy init, not at module import)
    from backend.web.services.event_store import init_event_store

    init_event_store()

    from backend.web.services.library_service import ensure_library_dir
    from backend.web.services.member_service import ensure_members_dir

    ensure_members_dir()
    ensure_library_dir()

    # ---- Entity-Chat repos + services ----
    _storage_strategy = os.getenv("LEON_STORAGE_STRATEGY", "sqlite")

    if _storage_strategy == "supabase":
        from backend.web.core.supabase_factory import create_supabase_client
        from storage.container import StorageContainer
        from storage.providers.supabase import (
            SupabaseAccountRepo,
            SupabaseChatEntityRepo,
            SupabaseChatMessageRepo,
            SupabaseChatRepo,
            SupabaseContactRepo,
            SupabaseEntityRepo,
            SupabaseInviteCodeRepo,
            SupabaseMemberRepo,
            SupabaseRecipeRepo,
            SupabaseThreadLaunchPrefRepo,
            SupabaseThreadRepo,
            SupabaseUserSettingsRepo,
        )

        _supabase_client = create_supabase_client()
        app.state.member_repo = SupabaseMemberRepo(_supabase_client)
        app.state.account_repo = SupabaseAccountRepo(_supabase_client)
        app.state.entity_repo = SupabaseEntityRepo(_supabase_client)
        app.state.thread_repo = SupabaseThreadRepo(_supabase_client)
        app.state.thread_launch_pref_repo = SupabaseThreadLaunchPrefRepo(_supabase_client)
        app.state.recipe_repo = SupabaseRecipeRepo(_supabase_client)
        app.state.chat_repo = SupabaseChatRepo(_supabase_client)
        app.state.chat_entity_repo = SupabaseChatEntityRepo(_supabase_client)
        app.state.chat_message_repo = SupabaseChatMessageRepo(_supabase_client)
        app.state.invite_code_repo = SupabaseInviteCodeRepo(_supabase_client)
        app.state.user_settings_repo = SupabaseUserSettingsRepo(_supabase_client)
        app.state._supabase_client = _supabase_client
        app.state._storage_container = StorageContainer(strategy="supabase", supabase_client=_supabase_client)
    else:
        from storage.providers.sqlite.chat_repo import SQLiteChatEntityRepo, SQLiteChatMessageRepo, SQLiteChatRepo
        from storage.providers.sqlite.entity_repo import SQLiteEntityRepo
        from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path
        from storage.providers.sqlite.member_repo import SQLiteAccountRepo, SQLiteMemberRepo
        from storage.providers.sqlite.recipe_repo import SQLiteRecipeRepo
        from storage.providers.sqlite.thread_launch_pref_repo import SQLiteThreadLaunchPrefRepo
        from storage.providers.sqlite.thread_repo import SQLiteThreadRepo

        db = resolve_role_db_path(SQLiteDBRole.MAIN)
        chat_db = resolve_role_db_path(SQLiteDBRole.CHAT)

        app.state.member_repo = SQLiteMemberRepo(db)
        app.state.account_repo = SQLiteAccountRepo(db)
        app.state.entity_repo = SQLiteEntityRepo(db)
        app.state.thread_repo = SQLiteThreadRepo(db)
        app.state.thread_launch_pref_repo = SQLiteThreadLaunchPrefRepo(db)
        app.state.recipe_repo = SQLiteRecipeRepo(db)
        app.state.chat_repo = SQLiteChatRepo(chat_db)
        app.state.chat_entity_repo = SQLiteChatEntityRepo(chat_db)
        app.state.chat_message_repo = SQLiteChatMessageRepo(chat_db)

    from backend.web.services.auth_service import AuthService

    if _storage_strategy == "supabase":
        app.state.auth_service = AuthService(
            members=app.state.member_repo,
            accounts=app.state.account_repo,
            entities=app.state.entity_repo,
            supabase_client=_supabase_client,
            invite_codes=app.state.invite_code_repo,
        )
    else:
        app.state.auth_service = AuthService(
            members=app.state.member_repo,
            accounts=app.state.account_repo,
            entities=app.state.entity_repo,
            supabase_client=None,
        )

    from backend.web.services.chat_events import ChatEventBus
    from backend.web.services.typing_tracker import TypingTracker

    app.state.chat_event_bus = ChatEventBus()
    app.state.typing_tracker = TypingTracker(app.state.chat_event_bus)

    from backend.web.services.delivery_resolver import DefaultDeliveryResolver

    if _storage_strategy == "supabase":
        app.state.contact_repo = SupabaseContactRepo(_supabase_client)
    else:
        from storage.providers.sqlite.contact_repo import SQLiteContactRepo

        app.state.contact_repo = SQLiteContactRepo(chat_db)

    delivery_resolver = DefaultDeliveryResolver(app.state.contact_repo, app.state.chat_entity_repo)

    from backend.web.services.chat_service import ChatService

    app.state.chat_service = ChatService(
        chat_repo=app.state.chat_repo,
        chat_entity_repo=app.state.chat_entity_repo,
        chat_message_repo=app.state.chat_message_repo,
        entity_repo=app.state.entity_repo,
        member_repo=app.state.member_repo,
        event_bus=app.state.chat_event_bus,
        delivery_resolver=delivery_resolver,
    )

    # Wire chat delivery after event loop is available
    from core.agents.communication.delivery import make_chat_delivery_fn

    app.state.chat_service.set_delivery_fn(make_chat_delivery_fn(app))

    # ---- Existing state ----
    app.state.queue_manager = MessageQueueManager()
    app.state.agent_pool: dict[str, Any] = {}
    app.state.thread_sandbox: dict[str, str] = {}
    app.state.thread_cwd: dict[str, str] = {}
    app.state.thread_locks: dict[str, asyncio.Lock] = {}
    app.state.thread_locks_guard = asyncio.Lock()
    app.state.thread_tasks: dict[str, asyncio.Task] = {}
    app.state.thread_event_buffers: dict[str, ThreadEventBuffer] = {}
    app.state.subagent_buffers: dict[str, RunEventBuffer] = {}

    from backend.web.services.display_builder import DisplayBuilder

    app.state.display_builder = DisplayBuilder()
    app.state.thread_last_active: dict[str, float] = {}  # thread_id → epoch timestamp
    app.state.idle_reaper_task: asyncio.Task | None = None
    app.state.cron_service = None
    app.state._event_loop = asyncio.get_running_loop()
    app.state.monitor_resources_task: asyncio.Task | None = None

    try:
        # Start idle reaper background task
        app.state.idle_reaper_task = asyncio.create_task(idle_reaper_loop(app))

        # Start resource overview refresh loop
        app.state.monitor_resources_task = asyncio.create_task(resource_overview_refresh_loop())

        # Start cron scheduler
        from backend.web.services.cron_service import CronService

        cron_svc = CronService()
        await cron_svc.start()
        app.state.cron_service = cron_svc

        # @@@wechat-registry — create registry with delivery callback, auto-start all
        from backend.web.services.wechat_service import WeChatConnectionRegistry
        from core.runtime.middleware.queue.formatters import format_wechat_message

        async def _wechat_deliver(conn, msg):
            """Delivery callback — routes WeChat messages to configured thread/chat."""
            routing = conn.routing
            if not routing.type or not routing.id:
                return
            sender_name = msg.from_user_id.split("@")[0] or msg.from_user_id
            if routing.type == "thread":
                from backend.web.services.message_routing import route_message_to_brain

                content = format_wechat_message(sender_name, msg.from_user_id, msg.text)
                await route_message_to_brain(app, routing.id, content, source="owner", sender_name=sender_name)
            elif routing.type == "chat":
                content = format_wechat_message(sender_name, msg.from_user_id, msg.text)
                app.state.chat_service.send_message(routing.id, conn.entity_id, content)

        app.state.wechat_registry = WeChatConnectionRegistry(delivery_fn=_wechat_deliver)
        app.state.wechat_registry.auto_start_all()

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

        # Cleanup: stop WeChat connections
        if hasattr(app.state, "wechat_registry"):
            await app.state.wechat_registry.shutdown()

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
