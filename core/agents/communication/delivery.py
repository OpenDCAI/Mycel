"""Chat delivery — enqueues lightweight notifications for agent threads.

v3: no full message text injected. Agent must read_messages to see content.
MessagingService._deliver_to_agents calls the delivery function for each
non-sender agent member.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from storage.contracts import MemberRow

logger = logging.getLogger(__name__)


def _resolve_recipient_thread_id(app: Any, recipient_id: str) -> str | None:
    thread = app.state.thread_repo.get_by_user_id(recipient_id)
    if thread is None:
        return None
    return thread["id"]


def make_chat_delivery_fn(app: Any):
    """Create a delivery callback for MessagingService.

    Uses qm.enqueue() + wake_handler to route notifications.
    No more route_fn injection from backend layer.
    """
    import asyncio

    loop = asyncio.get_running_loop()
    logger.info("[delivery] make_chat_delivery_fn: loop=%s", loop)

    def _deliver(
        recipient_id: str,
        member: MemberRow,
        content: str,
        sender_name: str,
        chat_id: str,
        sender_id: str,
        sender_avatar_url: str | None = None,
        signal: str | None = None,
    ) -> None:
        logger.info("[delivery] _deliver called: recipient=%s member=%s", recipient_id, member.id)
        future = asyncio.run_coroutine_threadsafe(
            _async_deliver(app, recipient_id, member, sender_name, chat_id, sender_id, sender_avatar_url, signal=signal),
            loop,
        )

        future.add_done_callback(functools.partial(_log_delivery_result, recipient_id))

    return _deliver


def _log_delivery_result(member_id: str, f: Any) -> None:
    """Done-callback for async delivery futures."""
    exc = f.exception()
    if exc:
        logger.error("[delivery] async delivery failed for %s: %s", member_id, exc, exc_info=exc)
    else:
        logger.info("[delivery] async delivery completed for %s", member_id)


async def _async_deliver(
    app: Any,
    recipient_id: str,
    member: MemberRow,
    sender_name: str,
    chat_id: str,
    sender_id: str,
    sender_avatar_url: str | None = None,
    signal: str | None = None,
) -> None:
    """Enqueue chat notification to an agent's brain thread.

    @@@v3-notification-only — no message content. Agent calls read_messages to see it.
    """
    from langchain_core.runnables.config import var_child_runnable_config

    var_child_runnable_config.set(None)

    # @@@thread-delivery-route - delivery target must come from the recipient social handle,
    # never from the template default-thread shortcut.
    thread_id = _resolve_recipient_thread_id(app, recipient_id)
    logger.info("[delivery] _async_deliver: recipient=%s member=%s thread=%s from=%s", recipient_id, member.id, thread_id, sender_name)
    from core.runtime.middleware.queue.formatters import format_chat_notification

    if not thread_id:
        logger.warning("Recipient %s has no thread, skipping delivery", recipient_id)
        return

    from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
    from backend.web.services.streaming_service import _ensure_thread_handlers

    sandbox_type = resolve_thread_sandbox(app, thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    _ensure_thread_handlers(agent, thread_id, app)

    typing_tracker = getattr(app.state, "typing_tracker", None)
    if typing_tracker is not None:
        typing_tracker.start_chat(thread_id, chat_id, recipient_id)

    unread_count = app.state.messaging_service.count_unread(chat_id, recipient_id)

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
