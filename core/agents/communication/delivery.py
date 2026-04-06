"""Chat delivery — enqueues lightweight notifications for agent threads.

v3: no full message text injected. Agent must read_messages to see content.
ChatService._deliver_to_agents calls the delivery function for each
non-sender agent member.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from storage.contracts import MemberRow

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
        member: MemberRow,
        content: str,
        sender_name: str,
        chat_id: str,
        sender_id: str,
        sender_avatar_url: str | None = None,
        signal: str | None = None,
    ) -> None:
        logger.info("[delivery] _deliver called: member=%s, thread=%s", member.id, member.main_thread_id)
        future = asyncio.run_coroutine_threadsafe(
            _async_deliver(app, member, sender_name, chat_id, sender_id, sender_avatar_url, signal=signal),
            loop,
        )

        future.add_done_callback(functools.partial(_log_delivery_result, member.id))

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

    logger.info("[delivery] _async_deliver: member=%s thread=%s from=%s", member.id, member.main_thread_id, sender_name)
    from core.runtime.middleware.queue.formatters import format_chat_notification

    if not member.main_thread_id:
        logger.warning("Member %s has no main_thread_id, skipping delivery", member.id)
        return

    thread_id = member.main_thread_id

    from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
    from backend.web.services.streaming_service import _ensure_thread_handlers

    sandbox_type = resolve_thread_sandbox(app, thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    _ensure_thread_handlers(agent, thread_id, app)

    typing_tracker = getattr(app.state, "typing_tracker", None)
    if typing_tracker is not None:
        typing_tracker.start_chat(thread_id, chat_id, member.id)

    unread_count = app.state.messaging_service.count_unread(chat_id, member.id)

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
