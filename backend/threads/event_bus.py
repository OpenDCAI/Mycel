from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

EventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
AsyncEventCallback = Callable[[dict[str, Any]], Awaitable[None]]
Unsubscribe = Callable[[], None]


class EventBus:
    """Thread-scoped publish/subscribe bus for agent activity events."""

    def __init__(self) -> None:
        self._subs: dict[str, list[EventCallback]] = {}

    def subscribe(self, thread_id: str, callback: EventCallback) -> Unsubscribe:
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

    async def publish(self, thread_id: str, event: dict[str, Any]) -> None:
        callbacks = list(self._subs.get(thread_id, []))
        for cb in callbacks:
            try:
                result = cb(event)
                if result is not None:
                    await result
            except Exception:
                logger.exception("[EventBus] subscriber error for thread %s", thread_id)

    def make_emitter(
        self,
        thread_id: str,
        agent_id: str = "",
        agent_name: str = "",
    ) -> AsyncEventCallback:
        async def _emit(event: dict[str, Any]) -> None:
            enriched = dict(event)
            if agent_id:
                enriched.setdefault("agent_id", agent_id)
            if agent_name:
                enriched.setdefault("agent_name", agent_name)
            await self.publish(thread_id, enriched)

        return _emit

    def clear_thread(self, thread_id: str) -> None:
        self._subs.pop(thread_id, None)

    def clear_all(self) -> None:
        self._subs.clear()


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
