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


def _seed_dev_user(app: FastAPI) -> None:
    """Create dev-user human member + initial agents if not yet seeded.

    Mirrors AuthService.register() but uses the fixed 'dev-user' ID that
    matches _DEV_PAYLOAD, so list_members('dev-user') returns results.
    """
    import logging
    import time
    from pathlib import Path

    from backend.web.services.member_service import MEMBERS_DIR, _write_agent_md, _write_json
    from storage.contracts import MemberRow, MemberType
    from storage.providers.sqlite.member_repo import generate_member_id

    log = logging.getLogger(__name__)
    member_repo = app.state.member_repo

    DEV_USER_ID = "dev-user"  # noqa: N806

    if member_repo.get_by_id(DEV_USER_ID) is not None:
        return  # already seeded

    log.info("DEV: seeding dev-user member + initial agents")
    now = time.time()

    # Human member row
    member_repo.create(
        MemberRow(
            id=DEV_USER_ID,
            name="Dev",
            type=MemberType.HUMAN,
            created_at=now,
        )
    )

    # Initial agents (same as register())
    initial_agents = [
        {"name": "Toad", "description": "Curious and energetic assistant", "avatar": "toad.jpeg"},
        {"name": "Morel", "description": "Thoughtful senior analyst", "avatar": "morel.jpeg"},
    ]
    assets_dir = Path(__file__).resolve().parents[3] / "assets"

    for agent_def in initial_agents:
        agent_id = generate_member_id()
        agent_dir = MEMBERS_DIR / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)
        _write_agent_md(agent_dir / "agent.md", name=agent_def["name"], description=agent_def["description"])
        _write_json(
            agent_dir / "meta.json",
            {
                "status": "active",
                "version": "1.0.0",
                "created_at": int(now * 1000),
                "updated_at": int(now * 1000),
            },
        )
        member_repo.create(
            MemberRow(
                id=agent_id,
                name=agent_def["name"],
                type=MemberType.MYCEL_AGENT,
                description=agent_def["description"],
                config_dir=str(agent_dir),
                owner_user_id=DEV_USER_ID,
                created_at=now,
            )
        )
        src_avatar = assets_dir / agent_def["avatar"]
        if src_avatar.exists():
            try:
                from backend.web.routers.entities import process_and_save_avatar

                avatar_path = process_and_save_avatar(src_avatar, agent_id)
                member_repo.update(agent_id, avatar=avatar_path, updated_at=now)
            except Exception as e:
                log.warning("DEV: avatar copy failed for %s: %s", agent_def["name"], e)


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

    app.state.auth_service = AuthService(
        members=app.state.member_repo,
        accounts=app.state.account_repo,
    )

    # Dev bypass: seed dev-user + initial agents on first startup
    from backend.web.core.dependencies import _DEV_SKIP_AUTH

    if _DEV_SKIP_AUTH:
        _seed_dev_user(app)

    from messaging.realtime.bridge import SupabaseRealtimeBridge
    from messaging.realtime.typing import TypingTracker as MessagingTypingTracker

    app.state.chat_event_bus = SupabaseRealtimeBridge()
    app.state.typing_tracker = MessagingTypingTracker(app.state.chat_event_bus)

    # Messaging system — Supabase-backed when SUPABASE env vars are available
    _supabase_url = os.getenv("SUPABASE_INTERNAL_URL") or os.getenv("SUPABASE_PUBLIC_URL")
    _supabase_key = os.getenv("LEON_SUPABASE_ANON_KEY") or os.getenv("LEON_SUPABASE_SERVICE_ROLE_KEY")
    _messaging_supabase_available = bool(_supabase_url and _supabase_key)

    if _messaging_supabase_available:
        from backend.web.core.supabase_factory import create_messaging_supabase_client
        from storage.providers.supabase.messaging_repo import (
            SupabaseChatMemberRepo,
            SupabaseMessageReadRepo,
            SupabaseMessagesRepo,
            SupabaseRelationshipRepo,
        )

        _supabase = create_messaging_supabase_client()
        _chat_member_repo = SupabaseChatMemberRepo(_supabase)
        _messages_repo = SupabaseMessagesRepo(_supabase)
        _message_read_repo = SupabaseMessageReadRepo(_supabase)
        app.state.relationship_repo = SupabaseRelationshipRepo(_supabase)

        from storage.providers.supabase.contact_repo import SupabaseContactRepo

        app.state.contact_repo = SupabaseContactRepo(_supabase)
    else:
        import logging as _logging

        _logging.getLogger(__name__).warning("Messaging Supabase client not configured — relationship/contact features unavailable.")
        _chat_member_repo = None
        _messages_repo = None
        _message_read_repo = None
        app.state.relationship_repo = None
        app.state.contact_repo = None

    from messaging.delivery.resolver import HireVisitDeliveryResolver

    delivery_resolver = HireVisitDeliveryResolver(
        contact_repo=app.state.contact_repo,
        chat_member_repo=_chat_member_repo,
        relationship_repo=app.state.relationship_repo,
    )

    from messaging.relationships.service import RelationshipService

    app.state.relationship_service = RelationshipService(
        app.state.relationship_repo,
        entity_repo=app.state.entity_repo,
    )

    from messaging.service import MessagingService

    app.state.messaging_service = MessagingService(
        chat_repo=app.state.chat_repo,
        chat_member_repo=_chat_member_repo,
        messages_repo=_messages_repo,
        message_read_repo=_message_read_repo,
        entity_repo=app.state.entity_repo,
        member_repo=app.state.member_repo,
        delivery_resolver=delivery_resolver,
        event_bus=app.state.chat_event_bus,
    )

    # Wire chat delivery after event loop is available
    from core.agents.communication.delivery import make_chat_delivery_fn

    _delivery_fn = make_chat_delivery_fn(app)
    app.state.messaging_service.set_delivery_fn(_delivery_fn)

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
