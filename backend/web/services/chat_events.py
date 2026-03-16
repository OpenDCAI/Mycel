"""Chat event bus — per-chat asyncio.Queue pub/sub."""

import asyncio
import logging

logger = logging.getLogger(__name__)


class ChatEventBus:
    """Per-chat pub/sub using asyncio.Queue per subscriber."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, chat_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(chat_id, []).append(queue)
        return queue

    def unsubscribe(self, chat_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(chat_id, [])
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._subscribers.pop(chat_id, None)

    def publish(self, chat_id: str, event: dict) -> None:
        """Publish event to all subscribers."""
        for queue in self._subscribers.get(chat_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Chat event queue full for chat %s", chat_id[:8])
