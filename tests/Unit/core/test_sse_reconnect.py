"""Tests for SSE reconnection + persistent event log.

Covers:
- EventStore: CRUD operations on run_events table
- serialize_message: msg.id inclusion
- observe_run_events: after-based filtering
"""

import asyncio
import sqlite3
from unittest.mock import patch

import pytest


@pytest.fixture()
def tmp_db(tmp_path):
    """Patch EventStore to use a temp DB file."""
    db_path = tmp_path / "test_leon.db"
    with patch("backend.web.services.event_store._DB_PATH", db_path):
        import backend.web.services.event_store as es

        es._conn = None
        es.init_event_store()
        yield db_path
        if es._conn is not None:
            asyncio.run(es._conn.close())
            es._conn = None


class TestEventStore:
    """EventStore CRUD operations."""

    def test_init_creates_table(self, tmp_db):
        # run_events live in events.db (sibling of the main DB)
        events_db = tmp_db.with_name("events.db")
        conn = sqlite3.connect(str(events_db))
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='run_events'").fetchall()
        assert len(tables) == 1

    def test_append_and_read(self, tmp_db):
        async def _run():
            from backend.web.services.event_store import append_event, read_events_after

            seq1 = await append_event("t1", "r1", {"event": "text", "data": '{"content":"hello"}'}, "msg-1")
            seq2 = await append_event("t1", "r1", {"event": "tool_call", "data": '{"id":"tc1"}'}, "msg-1")
            assert seq1 < seq2
            events = await read_events_after("t1", "r1", 0)
            assert len(events) == 2
            assert events[0]["event"] == "text"
            assert events[0]["message_id"] == "msg-1"
            assert events[1]["event"] == "tool_call"

        asyncio.run(_run())

    def test_read_after_filters(self, tmp_db):
        async def _run():
            from backend.web.services.event_store import append_event, read_events_after

            seq1 = await append_event("t1", "r1", {"event": "text", "data": "{}"})
            seq2 = await append_event("t1", "r1", {"event": "done", "data": "{}"})
            events = await read_events_after("t1", "r1", seq1)
            assert len(events) == 1
            assert events[0]["seq"] == seq2

        asyncio.run(_run())

    def test_get_latest_run_id(self, tmp_db):
        async def _run():
            from backend.web.services.event_store import append_event, get_latest_run_id

            assert await get_latest_run_id("t1") is None
            await append_event("t1", "run-a", {"event": "text", "data": "{}"})
            await append_event("t1", "run-b", {"event": "text", "data": "{}"})
            assert await get_latest_run_id("t1") == "run-b"

        asyncio.run(_run())

    def test_cleanup_old_runs(self, tmp_db):
        async def _run():
            from backend.web.services.event_store import append_event, cleanup_old_runs, read_events_after

            for run in ["r1", "r2", "r3"]:
                await append_event("t1", run, {"event": "text", "data": "{}"})
                await append_event("t1", run, {"event": "done", "data": ""})
            deleted = await cleanup_old_runs("t1", keep_latest=1)
            assert deleted == 4
            remaining = await read_events_after("t1", "r3", 0)
            assert len(remaining) == 2
            assert await read_events_after("t1", "r1", 0) == []
            assert await read_events_after("t1", "r2", 0) == []

        asyncio.run(_run())

    def test_cleanup_thread(self, tmp_db):
        async def _run():
            from backend.web.services.event_store import append_event, cleanup_thread, read_events_after

            await append_event("t1", "r1", {"event": "text", "data": "{}"})
            await append_event("t2", "r1", {"event": "text", "data": "{}"})
            deleted = await cleanup_thread("t1")
            assert deleted == 1
            assert await read_events_after("t1", "r1", 0) == []
            assert len(await read_events_after("t2", "r1", 0)) == 1

        asyncio.run(_run())

    def test_cross_thread_isolation(self, tmp_db):
        async def _run():
            from backend.web.services.event_store import append_event, read_events_after

            await append_event("t1", "r1", {"event": "text", "data": '{"content":"t1"}'})
            await append_event("t2", "r1", {"event": "text", "data": '{"content":"t2"}'})
            t1_events = await read_events_after("t1", "r1", 0)
            t2_events = await read_events_after("t2", "r1", 0)
            assert len(t1_events) == 1
            assert len(t2_events) == 1

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# serialize_message tests
# ---------------------------------------------------------------------------


class TestSerializeMessage:
    """serialize_message includes msg.id."""

    def test_includes_id(self):
        from backend.web.utils.serializers import serialize_message

        class AIMessage:
            id = "msg-uuid-123"
            content = "hello"
            tool_calls = []
            tool_call_id = None

        result = serialize_message(AIMessage())
        assert result["id"] == "msg-uuid-123"
        assert result["type"] == "AIMessage"
        assert result["content"] == "hello"

    def test_missing_id_returns_none(self):
        from backend.web.utils.serializers import serialize_message

        class HumanMessage:
            content = "hi"
            tool_calls = []
            tool_call_id = None

        result = serialize_message(HumanMessage())
        assert result["id"] is None


# ---------------------------------------------------------------------------
# RunEventBuffer + observe_run_events tests
# ---------------------------------------------------------------------------

import json


class TestObserveRunEvents:
    """observe_run_events with after-based filtering."""

    def test_observe_yields_all_events(self):
        async def _run():
            from backend.web.services.event_buffer import RunEventBuffer
            from backend.web.services.streaming_service import observe_run_events

            buf = RunEventBuffer()
            await buf.put({"event": "text", "data": json.dumps({"content": "hi", "_seq": 1})})
            await buf.put({"event": "done", "data": json.dumps({"thread_id": "t1", "_seq": 2})})
            await buf.mark_done()

            events = []
            async for ev in observe_run_events(buf):
                if "event" in ev:
                    events.append(ev)
            assert len(events) == 2

        asyncio.run(_run())

    def test_observe_after_skips_old_events(self):
        async def _run():
            from backend.web.services.event_buffer import RunEventBuffer
            from backend.web.services.streaming_service import observe_run_events

            buf = RunEventBuffer()
            await buf.put({"event": "text", "data": json.dumps({"content": "old", "_seq": 5})})
            await buf.put({"event": "text", "data": json.dumps({"content": "new", "_seq": 10})})
            await buf.put({"event": "done", "data": json.dumps({"thread_id": "t1", "_seq": 11})})
            await buf.mark_done()

            events = []
            async for ev in observe_run_events(buf, after=5):
                if "event" in ev:
                    events.append(ev)
            assert len(events) == 2
            assert json.loads(events[0]["data"])["content"] == "new"

        asyncio.run(_run())

    def test_buffer_run_id_field(self):
        from backend.web.services.event_buffer import RunEventBuffer

        buf = RunEventBuffer()
        assert buf.run_id == ""
        buf.run_id = "test-run-123"
        assert buf.run_id == "test-run-123"

    def test_read_with_timeout_returns_done_when_mark_done_happens_during_wait(self):
        async def _run():
            from backend.web.services.event_buffer import RunEventBuffer

            buf = RunEventBuffer()

            async def _mark_done_soon():
                await asyncio.sleep(0.05)
                await buf.mark_done()

            mark_task = asyncio.create_task(_mark_done_soon())
            events, cursor = await buf.read_with_timeout(0, timeout=1)
            await mark_task
            assert events == []
            assert cursor == 0

        asyncio.run(_run())
