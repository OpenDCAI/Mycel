"""Native Chat delivery handler for the Agent runtime."""

from __future__ import annotations

import logging
from typing import Any

from backend.protocols import agent_runtime as agent_runtime_protocol
from core.runtime.middleware.monitor import AgentState

logger = logging.getLogger(__name__)


class NativeAgentChatDeliveryHandler:
    """Routes Chat messages into native Mycel Agent threads."""

    def __init__(self, app: Any) -> None:
        self._app = app

    async def dispatch(self, envelope: agent_runtime_protocol.AgentChatDeliveryEnvelope) -> agent_runtime_protocol.AgentChatDeliveryResult:
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
            return agent_runtime_protocol.AgentChatDeliveryResult(status="skipped", thread_id=None, reason="missing_thread")

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
        return agent_runtime_protocol.AgentChatDeliveryResult(status="accepted", thread_id=thread_id)

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
