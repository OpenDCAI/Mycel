"""Bootstrap helpers for binding the Agent Runtime Gateway to app-backed handlers."""

from __future__ import annotations

from typing import Any

from backend.monitor.infrastructure.resources.resource_overview_cache import clear_resource_overview_cache
from backend.threads.activity_pool_service import get_or_create_agent, resolve_thread_sandbox
from backend.threads.chat_adapters.activity_reader import AppRuntimeThreadActivityReader
from backend.threads.chat_adapters.chat_handler import NativeAgentChatDeliveryHandler
from backend.threads.chat_adapters.chat_runtime_services import AppAgentChatRuntimeServices
from backend.threads.chat_adapters.gateway import NativeAgentRuntimeGateway
from backend.threads.chat_adapters.thread_handler import NativeAgentThreadInputHandler
from backend.threads.streaming import _ensure_thread_handlers, start_agent_run


def build_agent_runtime_gateway(app: Any, *, typing_tracker: Any) -> NativeAgentRuntimeGateway:
    app.state.agent_runtime_thread_activity_reader = AppRuntimeThreadActivityReader(
        thread_repo=app.state.thread_repo,
        agent_pool=app.state.agent_pool,
    )
    return NativeAgentRuntimeGateway(
        chat_handlers={
            "mycel": NativeAgentChatDeliveryHandler(
                runtime_services=AppAgentChatRuntimeServices(
                    app,
                    # @@@chat-runtime-borrowed-typing-tracker - threads runtime
                    # consumes chat-owned typing state, but the borrow happens at
                    # bootstrap so this gateway builder does not reach back
                    # through app.state for chat truth on its own.
                    typing_tracker=typing_tracker,
                    queue_manager=app.state.queue_manager,
                    get_or_create_agent=get_or_create_agent,
                    resolve_thread_sandbox=resolve_thread_sandbox,
                    ensure_thread_handlers=_ensure_thread_handlers,
                ),
            )
        },
        thread_input_handler=NativeAgentThreadInputHandler(
            app,
            queue_manager=app.state.queue_manager,
            thread_tasks=app.state.thread_tasks,
            thread_locks=app.state.thread_locks,
            thread_locks_guard=app.state.thread_locks_guard,
            get_or_create_agent=get_or_create_agent,
            resolve_thread_sandbox=resolve_thread_sandbox,
            start_agent_run=start_agent_run,
            clear_resource_overview_cache=clear_resource_overview_cache,
        ),
    )
