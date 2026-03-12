"""Conversation event bus — pub/sub for real-time conversation message events.

Subscribers get notified when new messages are created in a conversation,
whether from a user (API) or from an agent (logbook_reply).
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class ConversationEventBus:
    """Per-conversation pub/sub using asyncio.Queue per subscriber."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, conversation_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(conversation_id, []).append(queue)
        return queue

    def unsubscribe(self, conversation_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(conversation_id, [])
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._subscribers.pop(conversation_id, None)

    def publish(self, conversation_id: str, event: dict) -> None:
        """Publish event to all subscribers. Safe from event loop thread (sync)."""
        for queue in self._subscribers.get(conversation_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Conversation event queue full for %s, dropping event", conversation_id[:8])
