"""Chat delivery — routes chat messages to agent brain threads.

ChatService._deliver_to_agents calls the delivery function for each
non-sender agent entity. This module provides that function.
"""

from __future__ import annotations

import logging
from typing import Any

from storage.contracts import EntityRow

logger = logging.getLogger(__name__)


def make_chat_delivery_fn(app: Any):
    """Create a delivery callback for ChatService.

    Returns a sync function that schedules async delivery on the event loop.
    """
    import asyncio

    loop = asyncio.get_running_loop()
    logger.info("[delivery] make_chat_delivery_fn: loop=%s", loop)

    def _deliver(entity: EntityRow, content: str, sender_name: str, chat_id: str, sender_entity_id: str) -> None:
        logger.info("[delivery] _deliver called: entity=%s, thread=%s", entity.id, entity.thread_id)
        future = asyncio.run_coroutine_threadsafe(
            _async_deliver(app, entity, content, sender_name, chat_id, sender_entity_id),
            loop,
        )
        # Add callback to log errors
        def _on_done(f):
            exc = f.exception()
            if exc:
                logger.error("[delivery] async delivery failed for %s: %s", entity.id, exc, exc_info=exc)
            else:
                logger.info("[delivery] async delivery completed for %s", entity.id)
        future.add_done_callback(_on_done)

    return _deliver


async def _async_deliver(
    app: Any,
    entity: EntityRow,
    content: str,
    sender_name: str,
    chat_id: str,
    sender_entity_id: str,
) -> None:
    """Deliver chat message to an agent's brain thread."""
    from backend.web.services.message_routing import route_message_to_brain
    from backend.web.services.prompt_injection import build_message_with_hint
    from core.runtime.middleware.queue.formatters import format_chat_message

    if not entity.thread_id:
        logger.warning("Entity %s has no thread_id, skipping delivery", entity.id)
        return

    thread_id = entity.thread_id

    # @@@typing-lifecycle - start typing indicator
    typing_tracker = getattr(app.state, "typing_tracker", None)
    if typing_tracker is not None:
        typing_tracker.start_chat(thread_id, chat_id, entity.id)

    formatted = format_chat_message(content, sender_name, chat_id)
    formatted_with_hint = build_message_with_hint(formatted, source="external", sender_name=sender_name)

    await route_message_to_brain(
        app, thread_id, formatted_with_hint,
        source="external",
        sender_name=sender_name,
    )
