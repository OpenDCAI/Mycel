"""
Tests for subagent SSE event routing in _run_agent_to_buffer drain loop.

Verifies three properties:
  1. subagent_task_text/tool_call/tool_result do NOT go to parent buf (no leakage)
  2. subagent_task_start/done DO go to parent buf (lifecycle notification)
  3. Subagent SSE buffer receives the content events

Uses _run_agent_to_buffer directly with minimal mocks.
"""

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.web.services.event_buffer import RunEventBuffer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class CapturingDict(dict):
    """Dict that records every value ever set (survives pop)."""

    def __init__(self):
        super().__init__()
        self.history: dict = {}

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.history[key] = value


class MockRuntime:
    """Minimal runtime: captures event callback, ignores the rest."""

    def __init__(self):
        self._event_cb = None

    def set_event_callback(self, cb):
        self._event_cb = cb

    def get_status_dict(self):
        return {"state": "idle", "flags": []}

    def bind_thread(self, **_kwargs):
        pass

    def transition(self, _state):
        return True

    @property
    def current_state(self):
        from core.monitor import AgentState
        return AgentState.IDLE  # not ACTIVE → skip idle transition in finally

    def emit_activity_event(self, _event: dict):
        pass  # run_done notification — not relevant to routing tests

    def emit(self, event: dict):
        if self._event_cb:
            self._event_cb(event)


def _ai_chunk(text: str):
    chunk = MagicMock()
    chunk.__class__.__name__ = "AIMessageChunk"
    chunk.content = text
    chunk.id = f"msg-{uuid.uuid4().hex[:8]}"
    return chunk


def make_agent(activity_events: list[dict], *, parent_text: str = "parent reply"):
    """
    Agent whose astream() yields one parent text chunk, then emits
    all activity_events through the registered callback, then yields
    a second chunk to trigger the drain loop.
    """
    runtime = MockRuntime()

    async def fake_astream(_input, config=None, stream_mode=None):
        yield ("messages", (_ai_chunk(parent_text), {}))
        # push activity events into queue via the registered callback
        for ev in activity_events:
            runtime.emit(ev)
        yield ("messages", (_ai_chunk("end"), {}))

    agent_inner = MagicMock()
    agent_inner.astream = fake_astream

    agent = SimpleNamespace(
        runtime=runtime,
        agent=agent_inner,
        # no _sandbox → prime_sandbox skipped
        # no storage_container → _resolve_run_event_repo returns None
    )
    return agent


@pytest.fixture()
def tmp_db(tmp_path):
    """Redirect event_store to a temp DB."""
    db_path = tmp_path / "test.db"
    with patch("backend.web.services.event_store._DB_PATH", db_path):
        import backend.web.services.event_store as es

        es._default_run_event_repo = None
        es.init_event_store()
        yield db_path
        if es._default_run_event_repo is not None:
            es._default_run_event_repo.close()
            es._default_run_event_repo = None


@pytest.fixture()
def app():
    """Minimal app.state mock with capturing thread_event_buffers."""
    capturing = CapturingDict()
    return SimpleNamespace(
        state=SimpleNamespace(
            thread_event_buffers=capturing,
            activity_buffers={},
            thread_tasks={},
            queue_manager=MagicMock(),
            _event_loop=None,
        )
    )


async def _run(agent, thread_id, app, tmp_db):
    """Run _run_agent_to_buffer with all side-effect surfaces mocked."""
    from backend.web.services.streaming_service import _run_agent_to_buffer

    buf = RunEventBuffer()
    buf.run_id = str(uuid.uuid4())

    with (
        patch("backend.web.services.streaming_service._ensure_thread_handlers"),
        patch("backend.web.services.streaming_service.set_current_thread_id"),
        patch("backend.web.services.streaming_service.set_current_run_id"),
        patch("backend.web.utils.helpers.load_thread_config", return_value=None),
    ):
        await _run_agent_to_buffer(
            agent, thread_id, "test message", app, False, buf
        )

    return buf


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDrainLoopRouting:
    """Verify activity event routing through the drain loop."""

    @pytest.mark.asyncio
    async def test_subagent_text_not_in_parent_buf(self, tmp_db, app):
        """subagent_task_text must NOT appear in parent buf (no SSE leakage)."""
        task_id = "task-001"
        events = [
            {"event": "subagent_task_start", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}"}
            )},
            {"event": "subagent_task_text", "data": json.dumps(
                {"task_id": task_id, "content": "secret subagent content"}
            )},
            {"event": "subagent_task_done", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}", "status": "completed"}
            )},
        ]
        agent = make_agent(events)
        parent_buf = await _run(agent, "thread-A", app, tmp_db)

        parent_types = [e["event"] for e in parent_buf.events]
        assert "subagent_task_text" not in parent_types, (
            f"Leakage: subagent_task_text found in parent buf. All events: {parent_types}"
        )

    @pytest.mark.asyncio
    async def test_lifecycle_events_in_parent_buf(self, tmp_db, app):
        """subagent_task_start and subagent_task_done must go to parent buf."""
        task_id = "task-002"
        events = [
            {"event": "subagent_task_start", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}"}
            )},
            {"event": "subagent_task_done", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}", "status": "completed"}
            )},
        ]
        agent = make_agent(events)
        parent_buf = await _run(agent, "thread-B", app, tmp_db)

        parent_types = [e["event"] for e in parent_buf.events]
        assert "subagent_task_start" in parent_types
        assert "subagent_task_done" in parent_types

    @pytest.mark.asyncio
    async def test_subagent_text_goes_to_sa_buf(self, tmp_db, app):
        """subagent_task_text must appear in the subagent's RunEventBuffer."""
        task_id = "task-003"
        sa_thread_id = f"subagent_{task_id}"
        events = [
            {"event": "subagent_task_start", "data": json.dumps(
                {"task_id": task_id, "thread_id": sa_thread_id}
            )},
            {"event": "subagent_task_text", "data": json.dumps(
                {"task_id": task_id, "content": "hello"}
            )},
            {"event": "subagent_task_text", "data": json.dumps(
                {"task_id": task_id, "content": " world"}
            )},
            {"event": "subagent_task_done", "data": json.dumps(
                {"task_id": task_id, "thread_id": sa_thread_id, "status": "completed"}
            )},
        ]
        agent = make_agent(events)
        await _run(agent, "thread-C", app, tmp_db)

        # sa_buf is removed from thread_event_buffers on done, but CapturingDict retains it
        sa_buf = app.state.thread_event_buffers.history.get(sa_thread_id)
        assert sa_buf is not None, "Subagent buffer was never created"

        sa_types = [e["event"] for e in sa_buf.events]
        text_events = [e for e in sa_buf.events if e["event"] == "subagent_task_text"]
        assert len(text_events) == 2, f"Expected 2 text events in sa_buf, got {sa_types}"

    @pytest.mark.asyncio
    async def test_tool_call_and_result_not_in_parent_buf(self, tmp_db, app):
        """subagent_task_tool_call and tool_result must also not leak to parent."""
        task_id = "task-004"
        events = [
            {"event": "subagent_task_start", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}"}
            )},
            {"event": "subagent_task_tool_call", "data": json.dumps(
                {"task_id": task_id, "id": "tc-1", "name": "run_command", "args": {}}
            )},
            {"event": "subagent_task_tool_result", "data": json.dumps(
                {"task_id": task_id, "tool_call_id": "tc-1", "content": "hello"}
            )},
            {"event": "subagent_task_done", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}", "status": "completed"}
            )},
        ]
        agent = make_agent(events)
        parent_buf = await _run(agent, "thread-D", app, tmp_db)

        parent_types = [e["event"] for e in parent_buf.events]
        assert "subagent_task_tool_call" not in parent_types
        assert "subagent_task_tool_result" not in parent_types

    @pytest.mark.asyncio
    async def test_non_subagent_events_still_go_to_parent(self, tmp_db, app):
        """command_progress and other events must still reach parent buf."""
        task_id = "task-005"
        events = [
            {"event": "command_progress", "data": json.dumps({"output": "running..."})},
            {"event": "subagent_task_start", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}"}
            )},
            {"event": "subagent_task_done", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}", "status": "completed"}
            )},
        ]
        agent = make_agent(events)
        parent_buf = await _run(agent, "thread-E", app, tmp_db)

        parent_types = [e["event"] for e in parent_buf.events]
        assert "command_progress" in parent_types

    @pytest.mark.asyncio
    async def test_sa_buf_has_terminal_done_event(self, tmp_db, app):
        """Subagent buffer must have a terminal 'done' event so SSE consumer exits."""
        task_id = "task-006"
        sa_thread_id = f"subagent_{task_id}"
        events = [
            {"event": "subagent_task_start", "data": json.dumps(
                {"task_id": task_id, "thread_id": sa_thread_id}
            )},
            {"event": "subagent_task_done", "data": json.dumps(
                {"task_id": task_id, "thread_id": sa_thread_id, "status": "completed"}
            )},
        ]
        agent = make_agent(events)
        await _run(agent, "thread-F", app, tmp_db)

        sa_buf = app.state.thread_event_buffers.history.get(sa_thread_id)
        assert sa_buf is not None
        assert sa_buf.finished.is_set(), "sa_buf.mark_done() was not called"
        terminal = [e for e in sa_buf.events if e["event"] == "done"]
        assert len(terminal) == 1, f"Expected 1 terminal 'done' event, got {[e['event'] for e in sa_buf.events]}"


# ---------------------------------------------------------------------------
# Event-store verification (runs against real DB data if available)
# ---------------------------------------------------------------------------


class TestEventStoreVerification:
    """
    Verify that the drain loop path (run_id != 'activity_*') never wrote
    subagent_task_text to the parent thread in the real DB.

    Requires ~/.leon/leon.db from a live session with at least one subagent run.
    Skipped if DB unavailable.
    """

    REAL_DB = __import__("pathlib").Path.home() / ".leon" / "leon.db"

    @pytest.fixture(autouse=True)
    def skip_if_no_db(self):
        if not self.REAL_DB.exists():
            pytest.skip("~/.leon/leon.db not found")

    def _query(self, sql: str) -> list:
        import sqlite3
        conn = sqlite3.connect(str(self.REAL_DB))
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    # The fix (subagent SSE routing) was committed on 2026-03-03.
    # Old events in the DB predate the fix and are expected to contain leakage.
    FIX_DATE = "2026-03-03 14:00:00"

    def test_no_subagent_text_via_emit_path(self):
        """
        After the fix, subagent_task_text must NOT appear in parent buf
        via the emit() path (run_id not 'activity_*').

        Only checks events created on or after FIX_DATE to exclude pre-fix history.
        """
        rows = self._query(f"""
            SELECT thread_id, run_id, count(*) as cnt
            FROM run_events
            WHERE event_type = 'subagent_task_text'
              AND run_id NOT LIKE 'activity_%'
              AND created_at >= '{self.FIX_DATE}'
            GROUP BY thread_id, run_id
        """)
        assert rows == [], (
            f"subagent_task_text leaked via emit() path after fix: {rows}"
        )

    def test_subagent_start_done_present_via_emit_path(self):
        """
        At least one parent thread should have subagent lifecycle events via emit() path,
        confirming the routing is active and not vacuously passing.
        """
        rows = self._query("""
            SELECT count(*) FROM run_events
            WHERE event_type IN ('subagent_task_start', 'subagent_task_done')
              AND run_id NOT LIKE 'activity_%'
        """)
        count = rows[0][0]
        assert count > 0, (
            "No subagent_task_start/done via emit() path — "
            "either no subagent ran, or lifecycle events are also misrouted"
        )
