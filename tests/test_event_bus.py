"""Tests for backend/web/event_bus.py (P2 multi-agent event routing)."""

from __future__ import annotations

import asyncio

import pytest

from backend.web.event_bus import EventBus, get_event_bus


class TestEventBus:
    def test_subscribe_and_publish(self):
        async def _run():
            bus = EventBus()
            received = []

            async def cb(event):
                received.append(event)

            bus.subscribe("t1", cb)
            await bus.publish("t1", {"event": "text", "data": "hi"})
            assert len(received) == 1
            assert received[0]["event"] == "text"

        asyncio.run(_run())

    def test_unsubscribe(self):
        async def _run():
            bus = EventBus()
            received = []

            async def cb(event):
                received.append(event)

            unsub = bus.subscribe("t1", cb)
            unsub()
            await bus.publish("t1", {"event": "text"})
            assert received == []

        asyncio.run(_run())

    def test_multiple_subscribers(self):
        async def _run():
            bus = EventBus()
            r1, r2 = [], []

            async def cb1(event):
                r1.append(event)

            async def cb2(event):
                r2.append(event)

            bus.subscribe("t1", cb1)
            bus.subscribe("t1", cb2)
            await bus.publish("t1", {"event": "x"})
            assert len(r1) == 1
            assert len(r2) == 1

        asyncio.run(_run())

    def test_publish_to_different_threads_isolated(self):
        async def _run():
            bus = EventBus()
            r1, r2 = [], []

            async def cb1(event):
                r1.append(event)

            async def cb2(event):
                r2.append(event)

            bus.subscribe("t1", cb1)
            bus.subscribe("t2", cb2)
            await bus.publish("t1", {"event": "for-t1"})
            assert len(r1) == 1
            assert len(r2) == 0  # t2 not notified

        asyncio.run(_run())

    def test_make_emitter_enriches_agent_metadata(self):
        async def _run():
            bus = EventBus()
            received = []

            async def cb(event):
                received.append(event)

            bus.subscribe("t1", cb)
            emit = bus.make_emitter("t1", agent_id="agent-42", agent_name="coder")
            await emit({"event": "text", "data": "hello"})
            assert len(received) == 1
            assert received[0]["agent_id"] == "agent-42"
            assert received[0]["agent_name"] == "coder"

        asyncio.run(_run())

    def test_make_emitter_does_not_overwrite_existing_agent_id(self):
        async def _run():
            bus = EventBus()
            received = []

            async def cb(event):
                received.append(event)

            bus.subscribe("t1", cb)
            emit = bus.make_emitter("t1", agent_id="new", agent_name="new-name")
            # Event already has agent_id set — setdefault must preserve it
            await emit({"event": "x", "agent_id": "original"})
            assert received[0]["agent_id"] == "original"

        asyncio.run(_run())

    def test_clear_thread(self):
        async def _run():
            bus = EventBus()
            received = []

            async def cb(event):
                received.append(event)

            bus.subscribe("t1", cb)
            bus.clear_thread("t1")
            await bus.publish("t1", {"event": "x"})
            assert received == []

        asyncio.run(_run())

    def test_get_event_bus_singleton(self):
        b1 = get_event_bus()
        b2 = get_event_bus()
        assert b1 is b2
