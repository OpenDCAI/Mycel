"""Threads runtime bootstrap owned by the threads backend."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.threads.chat_adapters.bootstrap import build_agent_runtime_gateway
from core.runtime.middleware.queue import MessageQueueManager


def attach_threads_runtime(app: Any, storage_container: Any, *, typing_tracker: Any) -> None:
    app.state.queue_manager = MessageQueueManager(repo=storage_container.queue_repo())
    app.state.agent_pool = {}
    app.state.thread_sandbox = {}
    app.state.thread_cwd = {}
    app.state.thread_locks = {}
    app.state.thread_locks_guard = asyncio.Lock()
    app.state.thread_tasks = {}
    app.state.thread_event_buffers = {}
    app.state.subagent_buffers = {}
    app.state.thread_last_active = {}
    # @@@threads-bootstrap-borrowed-typing-tracker - threads runtime needs
    # chat-owned typing state for agent chat delivery, but the borrow is made
    # at bootstrap so downstream gateway setup does not reopen app.state.
    app.state.agent_runtime_gateway = build_agent_runtime_gateway(app, typing_tracker=typing_tracker)
