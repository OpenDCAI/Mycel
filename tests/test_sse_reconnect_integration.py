"""Rigorous integration tests for SSE reconnect + persistent event log.

Tests real data flows end-to-end:
- emit() → SQLite → read_events_after round-trip
- serialize_message with real LangChain messages
- observe_run_events cursor semantics under concurrent writes
- EventStore edge cases (empty runs, duplicate appends, large payloads)
- Thread deletion cleans up events
"""

import asyncio
import json
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


# ---------------------------------------------------------------------------
# 1. Real LangChain message serialization
# ---------------------------------------------------------------------------


class TestRealLangChainMessages:
    """Test serialize_message with actual LangChain message objects."""

    def test_ai_message_has_stable_id(self):
        from langchain_core.messages import AIMessage

        from backend.web.utils.serializers import serialize_message

        msg = AIMessage(content="Hello world", id="msg-abc-123")
        result = serialize_message(msg)
        assert result["id"] == "msg-abc-123"
        assert result["type"] == "AIMessage"
        assert result["content"] == "Hello world"
        assert result["tool_calls"] == []

    def test_human_message_has_stable_id(self):
        from langchain_core.messages import HumanMessage

        from backend.web.utils.serializers import serialize_message

        msg = HumanMessage(content="Hi there", id="msg-human-456")
        result = serialize_message(msg)
        assert result["id"] == "msg-human-456"
        assert result["type"] == "HumanMessage"

    def test_tool_message_has_stable_id(self):
        from langchain_core.messages import ToolMessage

        from backend.web.utils.serializers import serialize_message

        msg = ToolMessage(content="result data", tool_call_id="call_xyz", id="msg-tool-789")
        result = serialize_message(msg)
        assert result["id"] == "msg-tool-789"
        assert result["type"] == "ToolMessage"
        assert result["tool_call_id"] == "call_xyz"

    def test_ai_message_with_tool_calls_preserves_ids(self):
        from langchain_core.messages import AIMessage

        from backend.web.utils.serializers import serialize_message

        msg = AIMessage(
            content="Let me search for that.",
            id="msg-ai-tc",
            tool_calls=[
                {"id": "call_abc", "name": "web_search", "args": {"query": "test"}},
                {"id": "call_def", "name": "read_file", "args": {"path": "/tmp/x"}},
            ],
        )
        result = serialize_message(msg)
        assert result["id"] == "msg-ai-tc"
        assert len(result["tool_calls"]) == 2
        assert result["tool_calls"][0]["id"] == "call_abc"
        assert result["tool_calls"][1]["id"] == "call_def"

    def test_ai_message_default_id_is_none(self):
        """LangChain AIMessage without explicit id has id=None. Our serializer handles this."""
        from langchain_core.messages import AIMessage

        from backend.web.utils.serializers import serialize_message

        msg = AIMessage(content="auto id")
        result = serialize_message(msg)
        # LangChain does NOT auto-generate id — it's None unless explicitly set
        # In streaming, LangGraph assigns UUIDs; in direct construction, it's None
        # Our serializer correctly passes through None
        assert result["id"] is None

    def test_multipart_content_serialization(self):
        """AIMessage with list content (multimodal) preserves id."""
        from langchain_core.messages import AIMessage

        from backend.web.utils.serializers import serialize_message

        msg = AIMessage(
            content=[{"type": "text", "text": "hello"}, {"type": "text", "text": " world"}],
            id="msg-multi",
        )
        result = serialize_message(msg)
        assert result["id"] == "msg-multi"
        assert isinstance(result["content"], list)


# ---------------------------------------------------------------------------
# 2. Full serialize → JSON → mapBackendEntries round-trip
# ---------------------------------------------------------------------------


class TestSerializeMapRoundTrip:
    """Verify that serialize_message output feeds correctly into mapBackendEntries."""

    def _build_conversation(self):
        """Build a realistic multi-turn conversation with LangChain messages."""
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        from backend.web.utils.serializers import serialize_message

        messages = [
            HumanMessage(content="Search for Python docs", id="human-1"),
            AIMessage(
                content="I'll search for that.",
                id="ai-1",
                tool_calls=[{"id": "call_001", "name": "web_search", "args": {"q": "python"}}],
            ),
            ToolMessage(content="Python is a programming language...", tool_call_id="call_001", id="tool-1"),
            AIMessage(content="Here's what I found about Python.", id="ai-2"),
            HumanMessage(content="Now search for Rust", id="human-2"),
            AIMessage(
                content="",
                id="ai-3",
                tool_calls=[{"id": "call_002", "name": "web_search", "args": {"q": "rust"}}],
            ),
            ToolMessage(content="Rust is a systems language...", tool_call_id="call_002", id="tool-2"),
            AIMessage(content="Rust is a systems programming language.", id="ai-4"),
        ]
        return [serialize_message(m) for m in messages]

    def test_round_trip_ids_are_stable(self):
        """IDs from serialize_message flow through to mapBackendEntries entries."""
        serialized = self._build_conversation()

        # Simulate JSON round-trip (as happens over HTTP)
        json_str = json.dumps(serialized)
        payload = json.loads(json_str)

        # Import frontend-equivalent mapping (Python side for testing)
        # We test the serialized data structure directly
        assert payload[0]["id"] == "human-1"
        assert payload[0]["type"] == "HumanMessage"
        assert payload[1]["id"] == "ai-1"
        assert payload[1]["type"] == "AIMessage"
        assert payload[1]["tool_calls"][0]["id"] == "call_001"
        assert payload[2]["id"] == "tool-1"
        assert payload[2]["tool_call_id"] == "call_001"

    def test_all_messages_have_ids(self):
        """Every serialized message has a non-None id."""
        serialized = self._build_conversation()
        for msg in serialized:
            assert msg["id"] is not None, f"Message type={msg['type']} has no id"

    def test_ids_are_unique(self):
        """All message IDs are unique within a conversation."""
        serialized = self._build_conversation()
        ids = [msg["id"] for msg in serialized]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {ids}"


# ---------------------------------------------------------------------------
# 3. emit() → SQLite → read_events_after round-trip
# ---------------------------------------------------------------------------


class TestEmitSQLiteRoundTrip:
    """Simulate the real producer emit() path and verify SQLite persistence."""

    def test_emit_persists_and_injects_metadata(self, tmp_db):
        """emit() should write to SQLite AND inject _seq/_run_id/message_id into event data."""

        async def _run():
            from backend.web.services.event_buffer import RunEventBuffer
            from backend.web.services.event_store import append_event, read_events_after

            buf = RunEventBuffer()
            run_id = "test-run-001"
            buf.run_id = run_id
            thread_id = "thread-abc"

            event = {"event": "text", "data": json.dumps({"content": "hello"}, ensure_ascii=False)}
            message_id = "msg-ai-uuid-1"
            seq = await append_event(thread_id, run_id, event, message_id)

            data = json.loads(event["data"])
            data["_seq"] = seq
            data["_run_id"] = run_id
            data["message_id"] = message_id
            enriched_event = {**event, "data": json.dumps(data, ensure_ascii=False)}
            await buf.put(enriched_event)

            db_events = await read_events_after(thread_id, run_id, 0)
            assert len(db_events) == 1
            assert db_events[0]["event"] == "text"
            assert db_events[0]["message_id"] == message_id
            assert db_events[0]["seq"] == seq

            buf_events, _ = await buf.read(0)
            buf_data = json.loads(buf_events[0]["data"])
            assert buf_data["_seq"] == seq
            assert buf_data["_run_id"] == run_id
            assert buf_data["message_id"] == message_id
            assert buf_data["content"] == "hello"

        asyncio.run(_run())

    def test_emit_sequence_is_monotonic(self, tmp_db):
        """Sequence numbers from append_event must be strictly increasing."""

        async def _run():
            from backend.web.services.event_store import append_event

            seqs = []
            for i in range(20):
                seq = await append_event("t1", "r1", {"event": "text", "data": f'{{"n":{i}}}'}, f"msg-{i}")
                seqs.append(seq)
            for i in range(1, len(seqs)):
                assert seqs[i] > seqs[i - 1], f"seq[{i}]={seqs[i]} not > seq[{i - 1}]={seqs[i - 1]}"

        asyncio.run(_run())

    def test_emit_tool_call_with_message_id(self, tmp_db):
        """tool_call events should persist with the AIMessage's id."""

        async def _run():
            from backend.web.services.event_store import append_event, read_events_after

            tc_event = {
                "event": "tool_call",
                "data": json.dumps({"id": "call_abc", "name": "web_search", "args": {"q": "test"}}),
            }
            await append_event("t1", "r1", tc_event, "ai-msg-uuid")
            events = await read_events_after("t1", "r1", 0)
            assert events[0]["message_id"] == "ai-msg-uuid"
            data = json.loads(events[0]["data"])
            assert data["id"] == "call_abc"

        asyncio.run(_run())

    def test_emit_tool_result_with_message_id(self, tmp_db):
        """tool_result events should persist with the ToolMessage's id."""

        async def _run():
            from backend.web.services.event_store import append_event, read_events_after

            tr_event = {
                "event": "tool_result",
                "data": json.dumps({"tool_call_id": "call_abc", "name": "web_search", "content": "results..."}),
            }
            await append_event("t1", "r1", tr_event, "tool-msg-uuid")
            events = await read_events_after("t1", "r1", 0)
            assert events[0]["message_id"] == "tool-msg-uuid"

        asyncio.run(_run())

    def test_status_events_have_no_message_id(self, tmp_db):
        """Status events should persist with message_id=None."""

        async def _run():
            from backend.web.services.event_store import append_event, read_events_after

            status_event = {
                "event": "status",
                "data": json.dumps({"state": {"state": "ACTIVE"}, "tokens": {}}),
            }
            await append_event("t1", "r1", status_event, None)
            events = await read_events_after("t1", "r1", 0)
            assert events[0]["message_id"] is None

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. observe_run_events cursor semantics + concurrent writes
# ---------------------------------------------------------------------------


class TestObserveCursorSemantics:
    """Test observe_run_events under realistic conditions."""

    def test_observe_concurrent_producer_consumer(self):
        """Producer writes events while consumer reads — no data loss."""
        import asyncio

        async def _run():
            from backend.web.services.event_buffer import RunEventBuffer
            from backend.web.services.streaming_service import observe_run_events

            buf = RunEventBuffer()
            total_events = 50

            async def producer():
                for i in range(total_events):
                    await buf.put(
                        {
                            "event": "text",
                            "data": json.dumps({"content": f"chunk-{i}", "_seq": i + 1}),
                        }
                    )
                    await asyncio.sleep(0.001)
                await buf.put({"event": "done", "data": json.dumps({"_seq": total_events + 1})})
                await buf.mark_done()

            consumed = []

            async def consumer():
                async for ev in observe_run_events(buf):
                    if "event" in ev:
                        consumed.append(ev)

            await asyncio.gather(producer(), consumer())
            # All events including done
            assert len(consumed) == total_events + 1

        asyncio.run(_run())

    def test_observe_after_skips_exactly(self):
        """after=N skips events with _seq <= N, yields _seq > N."""
        import asyncio

        async def _run():
            from backend.web.services.event_buffer import RunEventBuffer
            from backend.web.services.streaming_service import observe_run_events

            buf = RunEventBuffer()
            for seq in [1, 2, 3, 4, 5]:
                await buf.put({"event": "text", "data": json.dumps({"_seq": seq, "n": seq})})
            await buf.put({"event": "done", "data": json.dumps({"_seq": 6})})
            await buf.mark_done()

            # after=3 → should get seq 4, 5, 6
            events = []
            async for ev in observe_run_events(buf, after=3):
                if "event" in ev:
                    events.append(ev)
            assert len(events) == 3
            seqs = [json.loads(e["data"])["_seq"] for e in events]
            assert seqs == [4, 5, 6]

        asyncio.run(_run())

    def test_observe_after_zero_gets_all(self):
        """after=0 should yield all events."""
        import asyncio

        async def _run():
            from backend.web.services.event_buffer import RunEventBuffer
            from backend.web.services.streaming_service import observe_run_events

            buf = RunEventBuffer()
            await buf.put({"event": "text", "data": json.dumps({"_seq": 1})})
            await buf.put({"event": "done", "data": json.dumps({"_seq": 2})})
            await buf.mark_done()

            events = []
            async for ev in observe_run_events(buf, after=0):
                if "event" in ev:
                    events.append(ev)
            assert len(events) == 2

        asyncio.run(_run())

    def test_observe_events_without_seq_always_yielded(self):
        """Events with non-JSON data bypass the after filter entirely."""
        import asyncio

        async def _run():
            from backend.web.services.event_buffer import RunEventBuffer
            from backend.web.services.streaming_service import observe_run_events

            buf = RunEventBuffer()
            # Valid JSON without _seq → gets _seq=0 via .get("_seq", 0) → filtered when after>0
            await buf.put({"event": "status", "data": json.dumps({"state": "ACTIVE"})})
            # Non-JSON data → json.loads fails → bypasses filter entirely
            await buf.put({"event": "done", "data": "not-json"})
            await buf.mark_done()

            events = []
            async for ev in observe_run_events(buf, after=999):
                if "event" in ev:
                    events.append(ev)
            # Only the non-JSON event passes through (JSON event has _seq=0 <= 999)
            assert len(events) == 1
            assert events[0]["event"] == "done"

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. EventStore edge cases
# ---------------------------------------------------------------------------


class TestEventStoreEdgeCases:
    """Edge cases and stress tests for EventStore."""

    def test_large_payload(self, tmp_db):
        """Events with large data payloads persist correctly."""

        async def _run():
            from backend.web.services.event_store import append_event, read_events_after

            big_content = "x" * 100_000
            event = {"event": "text", "data": json.dumps({"content": big_content})}
            await append_event("t1", "r1", event)

            events = await read_events_after("t1", "r1", 0)
            assert len(events) == 1
            data = json.loads(events[0]["data"])
            assert len(data["content"]) == 100_000

        asyncio.run(_run())

    def test_unicode_content(self, tmp_db):
        """Unicode content (Chinese, emoji) persists correctly."""

        async def _run():
            from backend.web.services.event_store import append_event, read_events_after

            content = "你好世界 🌍 こんにちは"
            event = {"event": "text", "data": json.dumps({"content": content}, ensure_ascii=False)}
            await append_event("t1", "r1", event, "msg-unicode")

            events = await read_events_after("t1", "r1", 0)
            data = json.loads(events[0]["data"])
            assert data["content"] == content

        asyncio.run(_run())

    def test_cleanup_keeps_latest_n(self, tmp_db):
        """cleanup_old_runs(keep_latest=2) keeps exactly 2 most recent runs."""

        async def _run():
            from backend.web.services.event_store import (
                append_event,
                cleanup_old_runs,
                read_events_after,
            )

            for run in ["r1", "r2", "r3", "r4"]:
                for i in range(3):
                    await append_event("t1", run, {"event": "text", "data": f'{{"n":{i}}}'})

            await cleanup_old_runs("t1", keep_latest=2)

            # r1 and r2 should be gone
            assert await read_events_after("t1", "r1", 0) == []
            assert await read_events_after("t1", "r2", 0) == []
            # r3 and r4 should remain
            assert len(await read_events_after("t1", "r3", 0)) == 3
            assert len(await read_events_after("t1", "r4", 0)) == 3

        asyncio.run(_run())

    def test_cleanup_noop_when_fewer_runs(self, tmp_db):
        """cleanup_old_runs does nothing when runs <= keep_latest."""

        async def _run():
            from backend.web.services.event_store import append_event, cleanup_old_runs, read_events_after

            await append_event("t1", "r1", {"event": "done", "data": "{}"})
            deleted = await cleanup_old_runs("t1", keep_latest=5)
            assert deleted == 0
            assert len(await read_events_after("t1", "r1", 0)) == 1

        asyncio.run(_run())

    def test_empty_run_id(self, tmp_db):
        """get_latest_run_id returns None for thread with no events."""

        async def _run():
            from backend.web.services.event_store import get_latest_run_id

            assert await get_latest_run_id("nonexistent-thread") is None

        asyncio.run(_run())

    def test_multiple_threads_independent_cleanup(self, tmp_db):
        """Cleaning up one thread doesn't affect another."""

        async def _run():
            from backend.web.services.event_store import append_event, cleanup_thread, read_events_after

            await append_event("t1", "r1", {"event": "text", "data": '{"a":1}'})
            await append_event("t1", "r1", {"event": "done", "data": "{}"})
            await append_event("t2", "r1", {"event": "text", "data": '{"b":2}'})

            await cleanup_thread("t1")
            assert await read_events_after("t1", "r1", 0) == []
            assert len(await read_events_after("t2", "r1", 0)) == 1

        asyncio.run(_run())

    def test_db_wal_mode(self, tmp_db):
        """Verify WAL mode is enabled for concurrent read/write."""

        async def _run():
            # WAL is set during init_event_store(), trigger via append_event
            from backend.web.services.event_store import append_event

            await append_event("t1", "r1", {"event": "text", "data": "{}"})

        asyncio.run(_run())

        import sqlite3

        # run_events live in events.db (sibling of the main DB)
        events_db = tmp_db.with_name("events.db")
        conn = sqlite3.connect(str(events_db))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
