"""Process-level EventBus for multi-agent event routing.

Architecture:
    Agent A ──┐
    Agent B ──┼──→ EventBus (routes by thread_id/agent_id) ──→ SSE ──→ Frontend
    Agent C ──┘

Core (LeonAgent) only holds an abstract `emit(event)` callback — it never
imports this module.  Backend wires the callback when starting a run.

Usage:
    # Backend (streaming_service.py): subscribe to a thread
    unsub = event_bus.subscribe(thread_id, callback)
    ...
    unsub()  # cleanup

    # LeonAgent (via AgentService): emit events for a child agent
    emit = event_bus.make_emitter(thread_id, agent_id="child-1")
    agent.runtime.bind_thread(activity_sink=emit)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Event callback signature: async (event: dict) -> None
EventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
Unsubscribe = Callable[[], None]


class EventBus:
    """Thread-scoped publish/subscribe bus for agent activity events.

    Each thread_id maps to a list of async callbacks. When an agent emits
    an event, all subscribers for that thread_id are notified.
    """

    def __init__(self) -> None:
        # thread_id → list of callbacks
        self._subs: dict[str, list[EventCallback]] = {}

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    def subscribe(self, thread_id: str, callback: EventCallback) -> Unsubscribe:
        """Subscribe to all events for `thread_id`.

        Returns an unsubscribe callable.
        """
        self._subs.setdefault(thread_id, []).append(callback)

        def _unsubscribe() -> None:
            subs = self._subs.get(thread_id, [])
            try:
                subs.remove(callback)
            except ValueError:
                pass
            if not subs:
                self._subs.pop(thread_id, None)

        return _unsubscribe

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(self, thread_id: str, event: dict[str, Any]) -> None:
        """Publish an event to all subscribers of `thread_id`."""
        callbacks = list(self._subs.get(thread_id, []))
        for cb in callbacks:
            try:
                result = cb(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("[EventBus] subscriber error for thread %s", thread_id)

    # ------------------------------------------------------------------
    # Emitter factory
    # ------------------------------------------------------------------

    def make_emitter(
        self,
        thread_id: str,
        agent_id: str = "",
        agent_name: str = "",
    ) -> EventCallback:
        """Return an async callable that enriches events with agent metadata and publishes them.

        This is injected into child LeonAgent.runtime as `activity_sink`.
        """

        async def _emit(event: dict[str, Any]) -> None:
            enriched = dict(event)
            if agent_id:
                enriched.setdefault("agent_id", agent_id)
            if agent_name:
                enriched.setdefault("agent_name", agent_name)
            await self.publish(thread_id, enriched)

        return _emit

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear_thread(self, thread_id: str) -> None:
        """Remove all subscriptions for a thread (call when SSE stream ends)."""
        self._subs.pop(thread_id, None)

    def clear_all(self) -> None:
        self._subs.clear()


# ---------------------------------------------------------------------------
# Process-level singleton — backend wires agents/subscribers to this instance
# ---------------------------------------------------------------------------

_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the process-level EventBus singleton."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
