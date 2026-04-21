from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_activity_bridge_attaches_drains_and_detaches_runtime_events() -> None:
    from backend.threads.run.activity_bridge import build_activity_bridge

    emitted: list[dict[str, str]] = []

    async def emit(event: dict[str, str]) -> None:
        emitted.append(event)

    runtime = SimpleNamespace(callback=None)

    def set_event_callback(callback) -> None:
        runtime.callback = callback

    runtime.set_event_callback = set_event_callback

    drain, attach, detach = build_activity_bridge(runtime=runtime, emit=emit)

    attach()
    assert runtime.callback is not None

    runtime.callback({"event": "notice", "data": "one"})
    runtime.callback({"event": "notice", "data": "two"})
    await drain()

    assert emitted == [
        {"event": "notice", "data": "one"},
        {"event": "notice", "data": "two"},
    ]

    detach()
    assert runtime.callback is None


@pytest.mark.asyncio
async def test_activity_bridge_drops_events_after_queue_is_full() -> None:
    from backend.threads.run.activity_bridge import build_activity_bridge

    emitted: list[dict[str, int]] = []

    async def emit(event: dict[str, int]) -> None:
        emitted.append(event)

    runtime = SimpleNamespace(callback=None)
    runtime.set_event_callback = lambda callback: setattr(runtime, "callback", callback)

    drain, attach, _detach = build_activity_bridge(runtime=runtime, emit=emit, maxsize=2)

    attach()
    runtime.callback({"event": 1})
    runtime.callback({"event": 2})
    runtime.callback({"event": 3})

    await drain()

    assert emitted == [{"event": 1}, {"event": 2}]
