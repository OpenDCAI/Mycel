"""Native direct Thread input handler for the Agent runtime."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.runtime.middleware.monitor import AgentState
from protocols import agent_runtime as agent_runtime_protocol

logger = logging.getLogger(__name__)


class NativeAgentThreadInputHandler:
    """Routes direct thread input into native Mycel Agent runs."""

    def __init__(
        self,
        app: Any,
        *,
        queue_manager: Any,
        thread_tasks: dict[str, Any],
        thread_locks: dict[str, asyncio.Lock],
        thread_locks_guard: asyncio.Lock,
    ) -> None:
        self._app = app
        self._queue_manager = queue_manager
        self._thread_tasks = thread_tasks
        self._thread_locks = thread_locks
        self._thread_locks_guard = thread_locks_guard

    async def dispatch(self, envelope: agent_runtime_protocol.AgentThreadInputEnvelope) -> agent_runtime_protocol.AgentThreadInputResult:
        from backend.monitor.infrastructure.resources.resource_overview_cache import clear_resource_overview_cache
        from backend.threads.activity_pool_service import get_or_create_agent, resolve_thread_sandbox
        from backend.threads.streaming import start_agent_run

        thread_id = envelope.thread_id
        startup_cancel = None
        existing_task = self._thread_tasks.get(thread_id)
        if existing_task is None or existing_task.done():
            startup_cancel = asyncio.get_running_loop().create_future()
            self._thread_tasks[thread_id] = startup_cancel

        try:
            sandbox_type = resolve_thread_sandbox(self._app, thread_id)
            agent = await get_or_create_agent(self._app, sandbox_type, thread_id=thread_id)
            qm = self._queue_manager

            if startup_cancel is not None and startup_cancel.cancelled():
                return agent_runtime_protocol.AgentThreadInputResult(status="cancelled", routing="cancelled", thread_id=thread_id)

            state = agent.runtime.current_state
            logger.debug("[agent-runtime-gateway] thread=%s state=%s source=%s", thread_id[:15], state, envelope.sender.source)

            if agent.runtime.current_state == AgentState.ACTIVE:
                qm.enqueue(
                    envelope.message.content,
                    thread_id,
                    "steer",
                    source=envelope.sender.source,
                    sender_name=envelope.sender.display_name,
                    sender_avatar_url=envelope.sender.avatar_url,
                    is_steer=True,
                )
                logger.debug("[agent-runtime-gateway] thread input enqueued")
                return agent_runtime_protocol.AgentThreadInputResult(status="injected", routing="steer", thread_id=thread_id)

            locks = self._thread_locks
            async with self._thread_locks_guard:
                lock = locks.setdefault(thread_id, asyncio.Lock())
            async with lock:
                if not agent.runtime.transition(AgentState.ACTIVE):
                    qm.enqueue(
                        envelope.message.content,
                        thread_id,
                        "steer",
                        source=envelope.sender.source,
                        sender_name=envelope.sender.display_name,
                        sender_avatar_url=envelope.sender.avatar_url,
                        is_steer=True,
                    )
                    logger.debug("[agent-runtime-gateway] thread input enqueued after transition race")
                    return agent_runtime_protocol.AgentThreadInputResult(status="injected", routing="steer", thread_id=thread_id)
                logger.debug("[agent-runtime-gateway] thread input starts run")
                meta = {
                    "source": envelope.sender.source,
                    "sender_name": envelope.sender.display_name,
                    "sender_avatar_url": envelope.sender.avatar_url,
                }
                if envelope.message.metadata:
                    meta.update(envelope.message.metadata)
                if envelope.message.attachments:
                    meta["attachments"] = envelope.message.attachments
                run_id = start_agent_run(
                    agent,
                    thread_id,
                    envelope.message.content,
                    self._app,
                    enable_trajectory=envelope.enable_trajectory,
                    message_metadata=meta,
                )
                # @@@monitor-resource-cache-run-start - a fresh run can create or resume a sandbox runtime immediately.
                # Drop the cached monitor snapshot so the next /api/monitor/resources read reflects the live topology.
                clear_resource_overview_cache()
            return agent_runtime_protocol.AgentThreadInputResult(status="started", routing="direct", run_id=run_id, thread_id=thread_id)
        finally:
            if startup_cancel is not None and self._thread_tasks.get(thread_id) is startup_cancel:
                self._thread_tasks.pop(thread_id, None)
