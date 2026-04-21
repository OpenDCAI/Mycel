"""Runtime activity-event bridge helpers for thread runs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


def build_activity_bridge(
    *,
    runtime: Any | None,
    emit: Callable[[dict[str, Any]], Awaitable[None]],
    maxsize: int = 1000,
) -> tuple[Callable[[], Awaitable[None]], Callable[[], None], Callable[[], None]]:
    """Build queue-backed runtime event attach/drain/detach helpers."""
    activity_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)

    def on_activity_event(event: dict[str, Any]) -> None:
        try:
            activity_queue.put_nowait(event)
        except asyncio.QueueFull:
            return

    async def drain() -> None:
        while not activity_queue.empty():
            try:
                act_event = activity_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            logger.info("[stream:drain] emitting activity event: %s", act_event.get("event", "?"))
            await emit(act_event)

    def attach() -> None:
        if runtime is None:
            return
        runtime.set_event_callback(on_activity_event)

    def detach() -> None:
        if runtime is None:
            return
        runtime.set_event_callback(None)

    return drain, attach, detach
