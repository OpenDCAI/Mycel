"""SupabaseRealtimeBridge — event bus backed by Supabase Broadcast.

Replaces ChatEventBus for typing indicators and process-level pub/sub.
For message persistence, Supabase Postgres Changes handles delivery directly
to the frontend via @supabase/supabase-js subscriptions.

This bridge:
1. Implements the same publish/subscribe interface as ChatEventBus
2. Routes typing events through Supabase Broadcast channels
3. Falls back to in-process asyncio.Queue for local subscribers (SSE compat)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SupabaseRealtimeBridge:
    """Hybrid event bus: local asyncio.Queue + Supabase Broadcast for typing."""

    def __init__(self, supabase_client: Any | None = None) -> None:
        self._supabase = supabase_client
        # Local subscribers for SSE fallback
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, chat_id: str) -> asyncio.Queue:
        """Subscribe to events for a chat (SSE / local consumer)."""
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
        """Publish event to local subscribers and Supabase Broadcast."""
        # Local delivery (SSE consumers)
        for queue in self._subscribers.get(chat_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("[realtime] queue full for chat %s", chat_id[:8])

        # Supabase Broadcast (typing indicators, not messages — messages go via Postgres Changes)
        event_type = event.get("event", "")
        if self._supabase and event_type in ("typing_start", "typing_stop"):
            try:
                channel = self._supabase.channel(f"chat:{chat_id}")
                channel.send_broadcast(event_type, event.get("data", {}))
            except Exception as e:
                logger.debug("[realtime] broadcast send failed: %s", e)
