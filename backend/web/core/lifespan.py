"""Application lifespan management."""

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from backend.web.services.event_buffer import RunEventBuffer
from backend.web.services.idle_reaper import idle_reaper_loop
from core.queue import MessageQueueManager
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

    from backend.web.services.member_service import ensure_members_dir
    from backend.web.services.library_service import ensure_library_dir

    ensure_members_dir()
    ensure_library_dir()

    # Initialize app state
    app.state.queue_manager = MessageQueueManager()
    app.state.agent_pool: dict[str, Any] = {}
    app.state.thread_sandbox: dict[str, str] = {}
    app.state.thread_cwd: dict[str, str] = {}
    app.state.thread_locks: dict[str, asyncio.Lock] = {}
    app.state.thread_locks_guard = asyncio.Lock()
    app.state.thread_tasks: dict[str, asyncio.Task] = {}
    app.state.thread_event_buffers: dict[str, RunEventBuffer] = {}
    app.state.activity_buffers: dict[str, RunEventBuffer] = {}
    app.state.idle_reaper_task: asyncio.Task | None = None
    app.state.cron_service = None
    app.state._event_loop = asyncio.get_running_loop()

    try:
        # Start idle reaper background task
        app.state.idle_reaper_task = asyncio.create_task(idle_reaper_loop(app))

        # Start cron scheduler
        from backend.web.services.cron_service import CronService

        cron_svc = CronService()
        await cron_svc.start()
        app.state.cron_service = cron_svc

        yield
    finally:
        # Cleanup: stop cron scheduler
        if app.state.cron_service:
            await app.state.cron_service.stop()

        # Cleanup: stop idle reaper
        task = app.state.idle_reaper_task
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Cleanup: close all agents
        for agent in app.state.agent_pool.values():
            try:
                agent.close()
            except Exception as e:
                print(f"[web] Agent cleanup error: {e}")
