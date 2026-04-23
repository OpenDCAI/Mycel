"""Bootstrap helpers for binding the Agent Runtime Gateway to app-backed handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.monitor.infrastructure.resources.resource_overview_cache import clear_resource_overview_cache
from backend.threads.activity_pool_service import get_or_create_agent, resolve_thread_sandbox
from backend.threads.chat_adapters.activity_reader import AppRuntimeThreadActivityReader
from backend.threads.chat_adapters.chat_handler import NativeAgentChatDeliveryHandler
from backend.threads.chat_adapters.chat_runtime_services import AppAgentChatRuntimeServices
from backend.threads.chat_adapters.gateway import NativeAgentRuntimeGateway
from backend.threads.chat_adapters.thread_handler import NativeAgentThreadInputHandler
from backend.threads.owner_reads import AppAgentActorLookup, AppHireConversationReader
from backend.threads.streaming import _ensure_thread_handlers, start_agent_run


@dataclass(frozen=True)
class AgentRuntimeGatewayState:
    gateway: NativeAgentRuntimeGateway
    activity_reader: Any
    conversation_reader: Any
    agent_actor_lookup: Any


def build_agent_runtime_state(
    app: Any,
    *,
    thread_repo: Any,
    typing_tracker: Any,
    messaging_service: Any | None = None,
) -> AgentRuntimeGatewayState:
    async def _get_or_create_runtime_agent(target_app: Any, sandbox_type: str, *, thread_id: str) -> Any:
        kwargs = {"thread_id": thread_id}
        if messaging_service is not None:
            kwargs["messaging_service"] = messaging_service
        return await get_or_create_agent(
            target_app,
            sandbox_type,
            **kwargs,
        )

    activity_reader = AppRuntimeThreadActivityReader(
        thread_repo=thread_repo,
        agent_pool=app.state.agent_pool,
    )
    conversation_reader = AppHireConversationReader(
        app,
        activity_reader=activity_reader,
    )
    agent_actor_lookup = AppAgentActorLookup(app)
    gateway = NativeAgentRuntimeGateway(
        chat_handlers={
            "mycel": NativeAgentChatDeliveryHandler(
                runtime_services=AppAgentChatRuntimeServices(
                    app,
                    # @@@chat-runtime-borrowed-typing-tracker - threads runtime
                    # consumes chat-owned typing state, but the borrow happens at
                    # bootstrap so this gateway builder does not reach back
                    # through app.state for chat truth on its own.
                    typing_tracker=typing_tracker,
                    thread_repo=thread_repo,
                    queue_manager=app.state.queue_manager,
                    get_or_create_agent=_get_or_create_runtime_agent,
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
            get_or_create_agent=_get_or_create_runtime_agent,
            resolve_thread_sandbox=resolve_thread_sandbox,
            start_agent_run=start_agent_run,
            clear_resource_overview_cache=clear_resource_overview_cache,
        ),
    )
    # @@@gateway-bootstrap-borrowable-state - gateway bootstrap now returns the
    # runtime handles without mirroring them onto loose app.state attrs, so
    # callers must keep borrowing through the bundle they just built.
    return AgentRuntimeGatewayState(
        gateway=gateway,
        activity_reader=activity_reader,
        conversation_reader=conversation_reader,
        agent_actor_lookup=agent_actor_lookup,
    )


def build_agent_runtime_gateway(
    app: Any,
    *,
    thread_repo: Any,
    typing_tracker: Any,
    messaging_service: Any | None = None,
) -> NativeAgentRuntimeGateway:
    return build_agent_runtime_state(
        app,
        thread_repo=thread_repo,
        typing_tracker=typing_tracker,
        messaging_service=messaging_service,
    ).gateway
