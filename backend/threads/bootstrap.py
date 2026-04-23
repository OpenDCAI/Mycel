"""Threads runtime bootstrap owned by the threads backend."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from backend.threads.chat_adapters.bootstrap import build_agent_runtime_state
from backend.threads.transport import build_inprocess_thread_input_transport
from core.runtime.middleware.queue import MessageQueueManager


@dataclass(frozen=True)
class ThreadsRuntimeState:
    thread_repo: Any
    queue_manager: Any
    typing_tracker: Any
    messaging_service: Any | None
    agent_runtime_gateway: Any
    thread_input_transport: Any
    activity_reader: Any
    conversation_reader: Any
    agent_actor_lookup: Any
    display_builder: Any | None = None
    event_loop: Any | None = None
    checkpoint_store: Any | None = None


def attach_threads_runtime(
    app: Any,
    storage_container: Any,
    *,
    thread_repo: Any,
    typing_tracker: Any,
    messaging_service: Any | None = None,
) -> ThreadsRuntimeState:
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
    runtime_state = build_agent_runtime_state(
        app,
        thread_repo=thread_repo,
        typing_tracker=typing_tracker,
        messaging_service=messaging_service,
    )
    app.state.threads_runtime_state = None
    # @@@threads-bootstrap-borrowable-state - threads runtime now exposes its
    # shared handles only through the returned/state bundle so downstream code
    # has one canonical read surface instead of loose app.state mirrors.
    state = ThreadsRuntimeState(
        thread_repo=thread_repo,
        queue_manager=app.state.queue_manager,
        typing_tracker=typing_tracker,
        messaging_service=messaging_service,
        agent_runtime_gateway=runtime_state.gateway,
        thread_input_transport=build_inprocess_thread_input_transport(runtime_gateway=runtime_state.gateway),
        activity_reader=runtime_state.activity_reader,
        conversation_reader=runtime_state.conversation_reader,
        agent_actor_lookup=runtime_state.agent_actor_lookup,
    )
    app.state.threads_runtime_state = state
    return state
