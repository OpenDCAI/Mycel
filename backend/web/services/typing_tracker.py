"""Typing indicator tracker — bridges agent run lifecycle to chat SSE.

Maps brain thread runs to chat typing events. Delivery calls start_chat(),
streaming_service finally block calls stop(). Thread-safe (single event loop).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.web.services.chat_events import ChatEventBus

logger = logging.getLogger(__name__)


@dataclass
class _ChatEntry:
    chat_id: str
    member_id: str


class TypingTracker:
    """Tracks which chat triggered each brain thread run."""

    def __init__(self, chat_event_bus: ChatEventBus) -> None:
        self._chat_bus = chat_event_bus
        self._active: dict[str, _ChatEntry] = {}

    def start_chat(self, thread_id: str, chat_id: str, member_id: str) -> None:
        """Start typing indicator for a chat-based delivery."""
        self._active[thread_id] = _ChatEntry(chat_id, member_id)
        self._chat_bus.publish(chat_id, {
            "event": "typing_start",
            "data": {"member_id": member_id},
        })

    def stop(self, thread_id: str) -> None:
        entry = self._active.pop(thread_id, None)
        if not entry:
            return
        self._chat_bus.publish(entry.chat_id, {
            "event": "typing_stop",
            "data": {"member_id": entry.member_id},
        })
