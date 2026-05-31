"""No-op EventBus — events are dropped.

The default when no delivery surface is wired. Hosts that stream to a UI
(e.g. Mycel's SSE bus) provide their own ``EventBusPort``.
"""

from __future__ import annotations

from typing import Any

from agent_core.ports.event_bus import EventBusPort, EventEmitter


class NullEventBus(EventBusPort):
    def make_emitter(self, thread_id: str, agent_id: str = "", agent_name: str = "") -> EventEmitter:
        async def _emit(event: dict[str, Any]) -> None:
            return None

        return _emit
