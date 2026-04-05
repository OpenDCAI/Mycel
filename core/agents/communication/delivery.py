"""Chat delivery — enqueues lightweight notifications for agent threads.

v3: no full message text injected. Agent must read_message to see content.
ChatService._deliver_to_agents calls the delivery function for each
non-sender agent entity.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from storage.contracts import EntityRow

logger = logging.getLogger(__name__)


def make_chat_delivery_fn(app: Any):
    """Create a delivery callback for ChatService.

    Uses qm.enqueue() + wake_handler to route notifications.
    No more route_fn injection from backend layer.
    """
    import asyncio

    loop = asyncio.get_running_loop()
    logger.info("[delivery] make_chat_delivery_fn: loop=%s", loop)

    def _deliver(
        entity: EntityRow,
        content: str,
        sender_name: str,
        chat_id: str,
        sender_id: str,
        sender_avatar_url: str | None = None,
        signal: str | None = None,
    ) -> None:
        logger.info("[delivery] _deliver called: entity=%s, thread=%s", entity.id, entity.thread_id)
        future = asyncio.run_coroutine_threadsafe(
            _async_deliver(app, entity, sender_name, chat_id, sender_id, sender_avatar_url, signal=signal),
            loop,
        )

        future.add_done_callback(functools.partial(_log_delivery_result, entity.id))

    return _deliver


def _log_delivery_result(entity_id: str, f: Any) -> None:
    """Done-callback for async delivery futures."""
    exc = f.exception()
    if exc:
        logger.error("[delivery] async delivery failed for %s: %s", entity_id, exc, exc_info=exc)
    else:
        logger.info("[delivery] async delivery completed for %s", entity_id)


async def _async_deliver(
    app: Any,
    entity: EntityRow,
    sender_name: str,
    chat_id: str,
    sender_id: str,
    sender_avatar_url: str | None = None,
    signal: str | None = None,
) -> None:
    """Enqueue chat notification to an agent's brain thread.

    @@@v3-notification-only — no message content. Agent calls read_message to see it.
    """
    # @@@context-isolation — clear inherited LangChain ContextVar so the recipient
    # agent's astream doesn't inherit the sender's StreamMessagesHandler callbacks.
    from langchain_core.runnables.config import var_child_runnable_config

    var_child_runnable_config.set(None)

    logger.info("[delivery] _async_deliver: entity=%s thread=%s from=%s", entity.id, entity.thread_id, sender_name)
    from core.runtime.middleware.queue.formatters import format_chat_notification

    if not entity.thread_id:
        logger.warning("Entity %s has no thread_id, skipping delivery", entity.id)
        return

    thread_id = entity.thread_id

    # @@@cold-wake — ensure agent + wake_handler exist before enqueue.
    # Without this, enqueue on an unvisited thread has no handler to wake the agent.
    from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
    from backend.web.services.streaming_service import _ensure_thread_handlers

    sandbox_type = resolve_thread_sandbox(app, thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    _ensure_thread_handlers(agent, thread_id, app)

    # @@@typing-lifecycle - start typing indicator
    typing_tracker = getattr(app.state, "typing_tracker", None)
    if typing_tracker is not None:
        typing_tracker.start_chat(thread_id, chat_id, entity.id)

    # Unread count for this recipient
    unread_count = app.state.chat_message_repo.count_unread(chat_id, entity.id)

    formatted = format_chat_notification(sender_name, chat_id, unread_count, signal=signal)

    qm = app.state.queue_manager
    qm.enqueue(
        formatted,
        thread_id,
        "chat",
        source="external",
        sender_id=sender_id,
        sender_name=sender_name,
        sender_avatar_url=sender_avatar_url,
    )
