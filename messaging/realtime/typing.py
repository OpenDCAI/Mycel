"""TypingTracker — Broadcast-backed typing indicator.

Same interface as backend/web/services/typing_tracker.py,
but routes through SupabaseRealtimeBridge (Broadcast) instead of ChatEventBus.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from messaging.realtime.bridge import SupabaseRealtimeBridge

logger = logging.getLogger(__name__)


@dataclass
class _ChatEntry:
    chat_id: str
    user_id: str


class TypingTracker:
    """Tracks which chat triggered each brain thread run, broadcasts typing events."""

    def __init__(self, bridge: "SupabaseRealtimeBridge") -> None:
        self._bridge = bridge
        self._active: dict[str, _ChatEntry] = {}

    def start_chat(self, thread_id: str, chat_id: str, user_id: str) -> None:
        self._active[thread_id] = _ChatEntry(chat_id, user_id)
        self._bridge.publish(chat_id, {
            "event": "typing_start",
            "data": {"user_id": user_id},
        })

    def stop(self, thread_id: str) -> None:
        entry = self._active.pop(thread_id, None)
        if not entry:
            return
        self._bridge.publish(entry.chat_id, {
            "event": "typing_stop",
            "data": {"user_id": entry.user_id},
        })
