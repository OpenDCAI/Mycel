from __future__ import annotations

import asyncio
from typing import Any

from core.runtime.middleware.monitor import AgentState
from protocols import agent_runtime as agent_runtime_protocol

from .runtime_metadata import thread_input_message_metadata, thread_input_metadata, thread_input_notification_type


class NativeAgentThreadInputHandler:
    def __init__(
        self,
        app: Any,
        *,
        queue_manager: Any,
        thread_tasks: dict[str, Any],
        thread_locks: dict[str, asyncio.Lock],
        thread_locks_guard: asyncio.Lock,
        get_or_create_agent: Any,
        resolve_thread_sandbox: Any,
        start_agent_run: Any,
        clear_resource_overview_cache: Any,
        typing_tracker: Any | None = None,
    ) -> None:
        self._app = app
        self._queue_manager = queue_manager
        self._thread_tasks = thread_tasks
        self._thread_locks = thread_locks
        self._thread_locks_guard = thread_locks_guard
        self._get_or_create_agent = get_or_create_agent
        self._resolve_thread_sandbox = resolve_thread_sandbox
        self._start_agent_run = start_agent_run
        self._clear_resource_overview_cache = clear_resource_overview_cache
        self._typing_tracker = typing_tracker

    async def dispatch(self, envelope: agent_runtime_protocol.AgentThreadInputEnvelope) -> agent_runtime_protocol.AgentThreadInputResult:
        thread_id = envelope.thread_id
        startup_cancel = None
        existing_task = self._thread_tasks.get(thread_id)
        if existing_task is None or existing_task.done():
            startup_cancel = asyncio.get_running_loop().create_future()
            self._thread_tasks[thread_id] = startup_cancel

        try:
            sandbox_type = self._resolve_thread_sandbox(self._app, thread_id)
            agent = await self._get_or_create_agent(self._app, sandbox_type, thread_id=thread_id)
            qm = self._queue_manager

            if startup_cancel is not None and startup_cancel.cancelled():
                return agent_runtime_protocol.AgentThreadInputResult(status="cancelled", routing="cancelled", thread_id=thread_id)

            state = agent.runtime.current_state
            meta = thread_input_metadata(envelope)
            queue_metadata = thread_input_message_metadata(envelope)
            notification_type = thread_input_notification_type(envelope)
            self._start_chat_notification(envelope, notification_type)

            if state == AgentState.ACTIVE:
                qm.enqueue(
                    envelope.message.content,
                    thread_id,
                    notification_type,
                    source=envelope.sender.source,
                    sender_id=envelope.sender.user_id,
                    sender_name=envelope.sender.display_name,
                    sender_avatar_url=envelope.sender.avatar_url,
                    is_steer=True,
                    metadata=queue_metadata,
                )
                return agent_runtime_protocol.AgentThreadInputResult(status="injected", routing="steer", thread_id=thread_id)

            locks = self._thread_locks
            async with self._thread_locks_guard:
                lock = locks.setdefault(thread_id, asyncio.Lock())
            async with lock:
                if not agent.runtime.transition(AgentState.ACTIVE):
                    qm.enqueue(
                        envelope.message.content,
                        thread_id,
                        notification_type,
                        source=envelope.sender.source,
                        sender_id=envelope.sender.user_id,
                        sender_name=envelope.sender.display_name,
                        sender_avatar_url=envelope.sender.avatar_url,
                        is_steer=True,
                        metadata=queue_metadata,
                    )
                    return agent_runtime_protocol.AgentThreadInputResult(status="injected", routing="steer", thread_id=thread_id)
                run_id = self._start_agent_run(
                    agent,
                    thread_id,
                    envelope.message.content,
                    self._app,
                    enable_trajectory=envelope.enable_trajectory,
                    message_metadata=meta,
                )
                # @@@monitor-resource-cache-run-start - a fresh run can create or resume a sandbox runtime immediately.
                # Drop the cached monitor snapshot so the next /api/monitor/resources read reflects the live topology.
                self._clear_resource_overview_cache()
            return agent_runtime_protocol.AgentThreadInputResult(status="started", routing="direct", run_id=run_id, thread_id=thread_id)
        finally:
            if startup_cancel is not None and self._thread_tasks.get(thread_id) is startup_cancel:
                self._thread_tasks.pop(thread_id, None)

    def _start_chat_notification(self, envelope: agent_runtime_protocol.AgentThreadInputEnvelope, notification_type: str) -> None:
        if notification_type != "chat" or self._typing_tracker is None:
            return
        metadata = envelope.message.metadata or {}
        chat_id = metadata.get("chat_id")
        recipient_user_id = metadata.get("recipient_user_id")
        if chat_id is None or recipient_user_id is None:
            raise RuntimeError("Chat thread input notification is missing chat_id or recipient_user_id metadata")
        self._typing_tracker.start_chat(envelope.thread_id, str(chat_id), str(recipient_user_id))
