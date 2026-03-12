"""Application lifespan management."""

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from backend.web.services.event_buffer import RunEventBuffer, ThreadEventBuffer
from backend.web.services.idle_reaper import idle_reaper_loop
from core.runtime.middleware.queue import MessageQueueManager
from backend.web.services.resource_cache import resource_overview_refresh_loop
from tui.config import ConfigManager


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

    # Initialize contact system repos + auth service
    from storage.providers.sqlite.contact_repo import SQLiteContactRepo
    from storage.providers.sqlite.conversation_repo import (
        SQLiteConversationMemberRepo,
        SQLiteConversationMessageRepo,
        SQLiteConversationRepo,
    )
    from storage.providers.sqlite.member_repo import SQLiteAccountRepo, SQLiteMemberRepo
    from backend.web.services.auth_service import AuthService

    app.state.member_repo = SQLiteMemberRepo()
    app.state.account_repo = SQLiteAccountRepo()
    app.state.contact_repo = SQLiteContactRepo()
    app.state.conversation_repo = SQLiteConversationRepo()
    app.state.conv_member_repo = SQLiteConversationMemberRepo()
    app.state.conv_message_repo = SQLiteConversationMessageRepo()
    app.state.auth_service = AuthService(
        members=app.state.member_repo,
        accounts=app.state.account_repo,
        contacts=app.state.contact_repo,
        conversations=app.state.conversation_repo,
        conv_members=app.state.conv_member_repo,
    )

    from backend.web.services.conversation_service import ConversationService

    app.state.conversation_service = ConversationService(
        conversations=app.state.conversation_repo,
        conv_members=app.state.conv_member_repo,
        conv_messages=app.state.conv_message_repo,
        contacts=app.state.contact_repo,
        members=app.state.member_repo,
    )

    # Initialize app state
    app.state.queue_manager = MessageQueueManager()
    app.state.agent_pool: dict[str, Any] = {}
    app.state.thread_sandbox: dict[str, str] = {}
    app.state.thread_cwd: dict[str, str] = {}
    app.state.thread_locks: dict[str, asyncio.Lock] = {}
    app.state.thread_locks_guard = asyncio.Lock()
    app.state.thread_tasks: dict[str, asyncio.Task] = {}
    app.state.thread_event_buffers: dict[str, ThreadEventBuffer] = {}
    app.state.subagent_buffers: dict[str, RunEventBuffer] = {}
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

        # Cleanup: close all agents
        for agent in app.state.agent_pool.values():
            try:
                agent.close()
            except Exception as e:
                print(f"[web] Agent cleanup error: {e}")
