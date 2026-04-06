"""Application lifespan management."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from backend.web.services.event_buffer import RunEventBuffer, ThreadEventBuffer
from backend.web.services.idle_reaper import idle_reaper_loop
from backend.web.services.resource_cache import resource_overview_refresh_loop
from config.env_manager import ConfigManager
from core.runtime.middleware.queue import MessageQueueManager
from storage.contracts import AccountRepo, MemberRepo


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

    # ---- Member-Chat repos + services ----
    _storage_strategy = os.getenv("LEON_STORAGE_STRATEGY", "sqlite")
    _supabase_client: Any | None = None
    _supabase_auth_client_factory: Any | None = None
    chat_db: Path | None = None
    member_repo: MemberRepo
    account_repo: AccountRepo

    if _storage_strategy == "supabase":
        from backend.web.core.supabase_factory import create_supabase_auth_client, create_supabase_client
        from storage.container import StorageContainer
        from storage.providers.supabase import (
            SupabaseChatMessageRepo,
            SupabaseChatParticipantRepo,
            SupabaseChatRepo,
            SupabaseContactRepo,
            SupabaseInviteCodeRepo,
            SupabaseMemberRepo,
            SupabaseRecipeRepo,
            SupabaseThreadLaunchPrefRepo,
            SupabaseThreadRepo,
            SupabaseUserSettingsRepo,
        )

        _supabase_client = create_supabase_client()
        _supabase_auth_client_factory = create_supabase_auth_client
        app.state.member_repo = SupabaseMemberRepo(_supabase_client)
        app.state.thread_repo = SupabaseThreadRepo(_supabase_client)
        app.state.thread_launch_pref_repo = SupabaseThreadLaunchPrefRepo(_supabase_client)
        app.state.recipe_repo = SupabaseRecipeRepo(_supabase_client)
        app.state.chat_repo = SupabaseChatRepo(_supabase_client)
        app.state.chat_participant_repo = SupabaseChatParticipantRepo(_supabase_client)
        app.state.chat_message_repo = SupabaseChatMessageRepo(_supabase_client)
        app.state.invite_code_repo = SupabaseInviteCodeRepo(_supabase_client)
        app.state.user_settings_repo = SupabaseUserSettingsRepo(_supabase_client)
        app.state._supabase_client = _supabase_client
        app.state._supabase_auth_client_factory = _supabase_auth_client_factory
        app.state._storage_container = StorageContainer(strategy="supabase", supabase_client=_supabase_client)
    else:
        from storage.providers.sqlite.chat_repo import SQLiteChatMessageRepo, SQLiteChatParticipantRepo, SQLiteChatRepo
        from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path
        from storage.providers.sqlite.member_repo import SQLiteMemberRepo
        from storage.providers.sqlite.recipe_repo import SQLiteRecipeRepo
        from storage.providers.sqlite.thread_launch_pref_repo import SQLiteThreadLaunchPrefRepo
        from storage.providers.sqlite.thread_repo import SQLiteThreadRepo

        db = resolve_role_db_path(SQLiteDBRole.MAIN)
        chat_db = resolve_role_db_path(SQLiteDBRole.CHAT)

        app.state.member_repo = SQLiteMemberRepo(db)
        app.state.thread_repo = SQLiteThreadRepo(db)
        app.state.thread_launch_pref_repo = SQLiteThreadLaunchPrefRepo(db)
        app.state.recipe_repo = SQLiteRecipeRepo(db)
        app.state.chat_repo = SQLiteChatRepo(chat_db)
        app.state.chat_participant_repo = SQLiteChatParticipantRepo(chat_db)
        app.state.chat_message_repo = SQLiteChatMessageRepo(chat_db)

    from backend.web.services.auth_service import AuthService

    if _storage_strategy == "supabase":
        assert _supabase_client is not None
        assert _supabase_auth_client_factory is not None
        app.state.auth_service = AuthService(
            members=app.state.member_repo,
            supabase_client=_supabase_client,
            supabase_auth_client_factory=_supabase_auth_client_factory,
            invite_codes=app.state.invite_code_repo,
        )
    else:
        app.state.auth_service = AuthService(
            members=app.state.member_repo,
        )

    from backend.web.services.chat_events import ChatEventBus
    from backend.web.services.typing_tracker import TypingTracker

    app.state.chat_event_bus = ChatEventBus()
    app.state.typing_tracker = TypingTracker(app.state.chat_event_bus)

    from backend.web.services.delivery_resolver import DefaultDeliveryResolver

    if _storage_strategy == "supabase":
        from storage.providers.supabase import SupabaseContactRepo

        assert _supabase_client is not None
        contact_repo = SupabaseContactRepo(_supabase_client)
    else:
        from storage.providers.sqlite.contact_repo import SQLiteContactRepo

        assert chat_db is not None
        contact_repo = SQLiteContactRepo(chat_db)

    app.state.contact_repo = contact_repo

    delivery_resolver = DefaultDeliveryResolver(app.state.contact_repo, app.state.chat_participant_repo)

    from backend.web.services.chat_service import ChatService

    app.state.chat_service = ChatService(
        chat_repo=app.state.chat_repo,
        chat_participant_repo=app.state.chat_participant_repo,
        chat_message_repo=app.state.chat_message_repo,
        member_repo=member_repo,
        event_bus=app.state.chat_event_bus,
        delivery_resolver=delivery_resolver,
    )

    # Wire chat delivery after event loop is available
    from core.agents.communication.delivery import make_chat_delivery_fn

    app.state.chat_service.set_delivery_fn(make_chat_delivery_fn(app))

    # ---- Messaging system (Supabase-backed) ----
    _msg_supabase_url = os.getenv("SUPABASE_INTERNAL_URL") or os.getenv("SUPABASE_PUBLIC_URL")
    _msg_supabase_key = os.getenv("LEON_SUPABASE_ANON_KEY") or os.getenv("LEON_SUPABASE_SERVICE_ROLE_KEY")
    _messaging_available = bool(_msg_supabase_url and _msg_supabase_key)

    if _messaging_available:
        from backend.web.core.supabase_factory import create_messaging_supabase_client
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

        app.state.relationship_service = RelationshipService(
            app.state.relationship_repo,
            member_repo=member_repo,
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
            member_repo=member_repo,
            event_bus=app.state.chat_event_bus,
            delivery_resolver=_msg_delivery_resolver,
        )
        app.state.messaging_service.set_delivery_fn(make_chat_delivery_fn(app))
    else:
        app.state.relationship_repo = None
        app.state.relationship_service = None
        app.state.messaging_service = None

    # ---- Existing state ----
    app.state.queue_manager = MessageQueueManager()
    agent_pool: dict[str, Any] = {}
    thread_sandbox: dict[str, str] = {}
    thread_cwd: dict[str, str] = {}
    thread_locks: dict[str, asyncio.Lock] = {}
    thread_tasks: dict[str, asyncio.Task[Any]] = {}
    thread_event_buffers: dict[str, ThreadEventBuffer] = {}
    subagent_buffers: dict[str, RunEventBuffer] = {}
    thread_last_active: dict[str, float] = {}
    idle_reaper_task: asyncio.Task[Any] | None = None
    monitor_resources_task: asyncio.Task[Any] | None = None
    app.state.agent_pool = agent_pool
    app.state.thread_sandbox = thread_sandbox
    app.state.thread_cwd = thread_cwd
    app.state.thread_locks = thread_locks
    app.state.thread_locks_guard = asyncio.Lock()
    app.state.thread_tasks = thread_tasks
    app.state.thread_event_buffers = thread_event_buffers
    app.state.subagent_buffers = subagent_buffers

    from backend.web.services.display_builder import DisplayBuilder

    app.state.display_builder = DisplayBuilder()
    app.state.thread_last_active = thread_last_active  # thread_id → epoch timestamp
    app.state.idle_reaper_task = idle_reaper_task
    app.state.cron_service = None
    app.state._event_loop = asyncio.get_running_loop()
    app.state.monitor_resources_task = monitor_resources_task

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
