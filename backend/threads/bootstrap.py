"""Threads runtime bootstrap owned by the threads backend."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from backend.threads.chat_adapters.bootstrap import build_agent_runtime_state
from core.runtime.middleware.queue import MessageQueueManager


@dataclass(frozen=True)
class ThreadsRuntimeState:
    queue_manager: Any
    agent_runtime_gateway: Any
    activity_reader: Any


def attach_threads_runtime(app: Any, storage_container: Any, *, typing_tracker: Any) -> ThreadsRuntimeState:
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
    runtime_state = build_agent_runtime_state(app, typing_tracker=typing_tracker)
    app.state.agent_runtime_gateway = runtime_state.gateway
    # @@@threads-bootstrap-borrowable-state - bootstrap still attaches thread
    # runtime objects onto app.state for the wider app, but it also returns the
    # freshly built runtime handles so enclosing lifespans do not need to reread them.
    return ThreadsRuntimeState(
        queue_manager=app.state.queue_manager,
        agent_runtime_gateway=app.state.agent_runtime_gateway,
        activity_reader=runtime_state.activity_reader,
    )
