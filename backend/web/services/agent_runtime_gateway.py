"""Agent-runtime gateway for service-to-service dispatch."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.protocols import agent_runtime as agent_runtime_protocol
from core.runtime.middleware.monitor import AgentState

logger = logging.getLogger(__name__)


class NativeAgentRuntimeGateway:
    """In-process Agent-side gateway for native Mycel runtime dispatch."""

    def __init__(self, app: Any) -> None:
        self._app = app

    async def dispatch_chat(
        self, envelope: agent_runtime_protocol.AgentChatDeliveryEnvelope
    ) -> agent_runtime_protocol.AgentGatewayDeliveryResult:
        from langchain_core.runnables.config import var_child_runnable_config

        var_child_runnable_config.set(None)

        # @@@thread-delivery-route - delivery target must come from the recipient social handle,
        # never from the template default-thread shortcut.
        thread_id = self._select_runtime_thread_id(envelope.recipient.agent_user_id)
        logger.info(
            "[agent-runtime-gateway] dispatch_chat: recipient=%s user=%s thread=%s from=%s",
            envelope.recipient.agent_user_id,
            envelope.recipient.agent_user_id,
            thread_id,
            envelope.sender.display_name,
        )

        if not thread_id:
            logger.warning("Recipient %s has no thread, skipping delivery", envelope.recipient.agent_user_id)
            return agent_runtime_protocol.AgentGatewayDeliveryResult(status="skipped", thread_id=None, reason="missing_thread")

        from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
        from backend.web.services.streaming_service import _ensure_thread_handlers
        from core.runtime.middleware.queue.formatters import format_chat_notification

        sandbox_type = resolve_thread_sandbox(self._app, thread_id)
        agent = await get_or_create_agent(self._app, sandbox_type, thread_id=thread_id)
        _ensure_thread_handlers(agent, thread_id, self._app)

        typing_tracker = getattr(self._app.state, "typing_tracker", None)
        if typing_tracker is not None:
            typing_tracker.start_chat(thread_id, envelope.chat.chat_id, envelope.recipient.agent_user_id)

        unread_count = self._app.state.messaging_service.count_unread(envelope.chat.chat_id, envelope.recipient.agent_user_id)
        formatted = format_chat_notification(
            envelope.sender.display_name,
            envelope.chat.chat_id,
            unread_count,
            signal=envelope.message.signal,
        )

        self._app.state.queue_manager.enqueue(
            formatted,
            thread_id,
            "chat",
            source="external",
            sender_id=envelope.sender.user_id,
            sender_name=envelope.sender.display_name,
            sender_avatar_url=envelope.sender.avatar_url,
        )
        return agent_runtime_protocol.AgentGatewayDeliveryResult(status="accepted", thread_id=thread_id)

    async def dispatch_thread_input(self, envelope: agent_runtime_protocol.AgentThreadInputEnvelope) -> dict[str, Any]:
        """Route direct thread input through the Agent-side gateway."""
        from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
        from backend.web.services.resource_cache import clear_resource_overview_cache
        from backend.web.services.streaming_service import start_agent_run

        thread_id = envelope.thread_id
        startup_cancel = None
        existing_task = self._app.state.thread_tasks.get(thread_id)
        if existing_task is None or existing_task.done():
            startup_cancel = asyncio.get_running_loop().create_future()
            self._app.state.thread_tasks[thread_id] = startup_cancel

        try:
            sandbox_type = resolve_thread_sandbox(self._app, thread_id)
            agent = await get_or_create_agent(self._app, sandbox_type, thread_id=thread_id)
            qm = self._app.state.queue_manager

            if startup_cancel is not None and startup_cancel.cancelled():
                return {"status": "cancelled", "routing": "cancelled", "thread_id": thread_id}

            state = agent.runtime.current_state
            logger.debug("[agent-runtime-gateway] thread=%s state=%s source=%s", thread_id[:15], state, envelope.source)

            if agent.runtime.current_state == AgentState.ACTIVE:
                qm.enqueue(
                    envelope.content,
                    thread_id,
                    "steer",
                    source=envelope.source,
                    sender_name=envelope.sender_name,
                    sender_avatar_url=envelope.sender_avatar_url,
                    is_steer=True,
                )
                logger.debug("[agent-runtime-gateway] thread input enqueued")
                return {"status": "injected", "routing": "steer", "thread_id": thread_id}

            locks = self._app.state.thread_locks
            async with self._app.state.thread_locks_guard:
                lock = locks.setdefault(thread_id, asyncio.Lock())
            async with lock:
                if not agent.runtime.transition(AgentState.ACTIVE):
                    qm.enqueue(
                        envelope.content,
                        thread_id,
                        "steer",
                        source=envelope.source,
                        sender_name=envelope.sender_name,
                        sender_avatar_url=envelope.sender_avatar_url,
                        is_steer=True,
                    )
                    logger.debug("[agent-runtime-gateway] thread input enqueued after transition race")
                    return {"status": "injected", "routing": "steer", "thread_id": thread_id}
                logger.debug("[agent-runtime-gateway] thread input starts run")
                meta = {
                    "source": envelope.source,
                    "sender_name": envelope.sender_name,
                    "sender_avatar_url": envelope.sender_avatar_url,
                }
                if envelope.message_metadata:
                    meta.update(envelope.message_metadata)
                if envelope.attachments:
                    meta["attachments"] = envelope.attachments
                run_id = start_agent_run(
                    agent,
                    thread_id,
                    envelope.content,
                    self._app,
                    enable_trajectory=envelope.enable_trajectory,
                    message_metadata=meta,
                )
                # @@@monitor-resource-cache-run-start - a fresh run can create or resume a sandbox runtime immediately.
                # Drop the cached monitor snapshot so the next /api/monitor/resources read reflects the live topology.
                clear_resource_overview_cache()
            return {"status": "started", "routing": "direct", "run_id": run_id, "thread_id": thread_id}
        finally:
            if startup_cancel is not None and self._app.state.thread_tasks.get(thread_id) is startup_cancel:
                self._app.state.thread_tasks.pop(thread_id, None)

    def _select_runtime_thread_id(self, recipient_id: str) -> str | None:
        thread = self._app.state.thread_repo.get_by_user_id(recipient_id)
        active_thread_id = self._resolve_unique_active_thread_id(recipient_id, thread)
        if active_thread_id is not None:
            return active_thread_id
        if thread is None:
            return None
        return thread["id"]

    def _resolve_unique_active_thread_id(self, recipient_id: str, thread: dict[str, Any] | None) -> str | None:
        agent_user_id = str((thread or {}).get("agent_user_id") or recipient_id).strip()
        if not agent_user_id:
            return None

        active_thread_ids: list[str] = []
        live_child_threads: list[tuple[int, str]] = []
        for candidate in self._app.state.thread_repo.list_by_agent_user(agent_user_id):
            thread_id = str(candidate.get("id") or "").strip()
            if not thread_id:
                continue
            # @@@active-thread-delivery-precedence - fresh chat delivery should prefer a
            # recipient's latest live child thread over the default-main thread, even when the
            # main thread is still marked ACTIVE from stale work or older child threads still exist.
            for pool_key, agent in self._app.state.agent_pool.items():
                if not str(pool_key).startswith(f"{thread_id}:"):
                    continue
                state = agent.runtime.current_state
                if state in {
                    AgentState.READY,
                    AgentState.ACTIVE,
                    AgentState.IDLE,
                    AgentState.SUSPENDED,
                    AgentState.INITIALIZING,
                } and not bool(candidate.get("is_main")):
                    live_child_threads.append((int(candidate.get("branch_index") or -1), thread_id))
                if state == AgentState.ACTIVE:
                    active_thread_ids.append(thread_id)
                    break

        if live_child_threads:
            return max(live_child_threads)[1]
        unique_active_thread_ids = list(dict.fromkeys(active_thread_ids))
        if len(unique_active_thread_ids) == 1:
            return unique_active_thread_ids[0]
        return None
