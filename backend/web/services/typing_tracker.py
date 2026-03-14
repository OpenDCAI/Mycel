"""Typing indicator tracker — bridges agent run lifecycle to conversation SSE.

Maps brain thread runs to conversation typing events. Delivery calls start(),
streaming_service finally block calls stop(). Thread-safe (single event loop).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.web.services.conversation_events import ConversationEventBus

logger = logging.getLogger(__name__)


class TypingTracker:
    """Tracks which conversation triggered each brain thread run."""

    def __init__(self, event_bus: ConversationEventBus) -> None:
        self._event_bus = event_bus
        # thread_id → (conversation_id, member_id)
        self._active: dict[str, tuple[str, str]] = {}

    def start(self, thread_id: str, conversation_id: str, member_id: str) -> None:
        self._active[thread_id] = (conversation_id, member_id)
        self._event_bus.publish(conversation_id, {
            "event": "typing_start",
            "member_id": member_id,
        })

    def stop(self, thread_id: str) -> None:
        entry = self._active.pop(thread_id, None)
        if entry:
            conversation_id, member_id = entry
            self._event_bus.publish(conversation_id, {
                "event": "typing_stop",
                "member_id": member_id,
            })
