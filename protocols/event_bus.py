"""Portable event-bus seam for top-level runtime consumers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]
EventBusFactory = Callable[[], "EventBusPort"]


class EventBusPort(Protocol):
    def make_emitter(
        self,
        thread_id: str,
        agent_id: str = "",
        agent_name: str = "",
    ) -> EventEmitter: ...
