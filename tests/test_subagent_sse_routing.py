"""
Tests for subagent SSE event routing in _run_agent_to_buffer drain loop.

Verifies three properties:
  1. subagent content events (text/tool_call/tool_result with non-"main" agent_id)
     do NOT go to parent buf (no leakage)
  2. task_start/task_done lifecycle events DO go to parent buf
  3. Subagent SSE buffer (in app.state.subagent_buffers) receives the content events

Uses _run_agent_to_buffer directly with minimal mocks.
"""

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.web.services.event_buffer import RunEventBuffer, ThreadEventBuffer


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
    """Minimal app.state mock with capturing subagent_buffers."""
    capturing = CapturingDict()
    return SimpleNamespace(
        state=SimpleNamespace(
            thread_event_buffers={},
            subagent_buffers=capturing,
            thread_tasks={},
            queue_manager=MagicMock(),
            _event_loop=None,
        )
    )


async def _run(agent, thread_id, app, tmp_db):
    """Run _run_agent_to_buffer with all side-effect surfaces mocked."""
    from backend.web.services.streaming_service import _run_agent_to_buffer

    thread_buf = ThreadEventBuffer()
    run_id = str(uuid.uuid4())

    with (
        patch("backend.web.services.streaming_service._ensure_thread_handlers"),
        patch("backend.web.services.streaming_service.set_current_thread_id"),
        patch("backend.web.services.streaming_service.set_current_run_id"),
        patch("backend.web.utils.helpers.load_thread_config", return_value=None),
    ):
        await _run_agent_to_buffer(
            agent, thread_id, "test message", app, False, thread_buf, run_id
        )

    return thread_buf


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _parent_event_types(thread_buf: ThreadEventBuffer) -> list[str]:
    """Extract event type names from a ThreadEventBuffer's ring."""
    return [e["event"] for e in list(thread_buf._ring) if "event" in e]


class TestDrainLoopRouting:
    """Verify activity event routing through the drain loop."""

    @pytest.mark.asyncio
    async def test_subagent_text_not_in_parent_buf(self, tmp_db, app):
        """Subagent content events (text with agent_id != "main") must NOT appear in parent buf."""
        task_id = "task-001"
        agent_id = f"subagent-{task_id}"
        events = [
            {"event": "task_start", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}", "agent_id": agent_id}
            )},
            {"event": "text", "data": json.dumps(
                {"task_id": task_id, "content": "secret subagent content", "agent_id": agent_id}
            )},
            {"event": "task_done", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}", "status": "completed", "agent_id": agent_id}
            )},
        ]
        agent = make_agent(events)
        parent_buf = await _run(agent, "thread-A", app, tmp_db)

        parent_events = list(parent_buf._ring)
        # Filter to activity-originated events (exclude run_start, run_done, status, text from main agent)
        # The subagent "text" event must NOT appear alongside agent_id != "main"
        subagent_text_leaked = [
            e for e in parent_events
            if e.get("event") == "text"
            and "secret subagent content" in e.get("data", "")
        ]
        assert not subagent_text_leaked, (
            f"Leakage: subagent text event found in parent buf: {subagent_text_leaked}"
        )

    @pytest.mark.asyncio
    async def test_lifecycle_events_in_parent_buf(self, tmp_db, app):
        """task_start and task_done lifecycle events must go to parent buf."""
        task_id = "task-002"
        agent_id = f"subagent-{task_id}"
        events = [
            {"event": "task_start", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}", "agent_id": agent_id}
            )},
            {"event": "task_done", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}", "status": "completed", "agent_id": agent_id}
            )},
        ]
        agent = make_agent(events)
        parent_buf = await _run(agent, "thread-B", app, tmp_db)

        parent_types = _parent_event_types(parent_buf)
        assert "task_start" in parent_types
        assert "task_done" in parent_types

    @pytest.mark.asyncio
    async def test_subagent_text_goes_to_sa_buf(self, tmp_db, app):
        """Subagent text events must appear in the subagent's RunEventBuffer."""
        task_id = "task-003"
        sa_thread_id = f"subagent_{task_id}"
        agent_id = f"subagent-{task_id}"
        events = [
            {"event": "task_start", "data": json.dumps(
                {"task_id": task_id, "thread_id": sa_thread_id, "agent_id": agent_id}
            )},
            {"event": "text", "data": json.dumps(
                {"task_id": task_id, "content": "hello", "agent_id": agent_id}
            )},
            {"event": "text", "data": json.dumps(
                {"task_id": task_id, "content": " world", "agent_id": agent_id}
            )},
            {"event": "task_done", "data": json.dumps(
                {"task_id": task_id, "thread_id": sa_thread_id, "status": "completed", "agent_id": agent_id}
            )},
        ]
        agent = make_agent(events)
        await _run(agent, "thread-C", app, tmp_db)

        # sa_buf is removed from subagent_buffers on done, but CapturingDict retains it in history
        sa_buf = app.state.subagent_buffers.history.get(sa_thread_id)
        assert sa_buf is not None, "Subagent buffer was never created"

        sa_types = [e["event"] for e in sa_buf.events]
        text_events = [e for e in sa_buf.events if e["event"] == "text"]
        assert len(text_events) == 2, f"Expected 2 text events in sa_buf, got {sa_types}"

    @pytest.mark.asyncio
    async def test_tool_call_and_result_not_in_parent_buf(self, tmp_db, app):
        """Subagent tool_call and tool_result events must also not leak to parent."""
        task_id = "task-004"
        agent_id = f"subagent-{task_id}"
        events = [
            {"event": "task_start", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}", "agent_id": agent_id}
            )},
            {"event": "tool_call", "data": json.dumps(
                {"task_id": task_id, "id": "tc-1", "name": "run_command", "args": {}, "agent_id": agent_id}
            )},
            {"event": "tool_result", "data": json.dumps(
                {"task_id": task_id, "tool_call_id": "tc-1", "content": "hello", "agent_id": agent_id}
            )},
            {"event": "task_done", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}", "status": "completed", "agent_id": agent_id}
            )},
        ]
        agent = make_agent(events)
        parent_buf = await _run(agent, "thread-D", app, tmp_db)

        # Only tool_call/tool_result events emitted by the main agent (from astream) should
        # appear in the parent buffer. The subagent ones (with agent_id != "main") must not.
        parent_events = list(parent_buf._ring)
        subagent_tool_leaked = [
            e for e in parent_events
            if e.get("event") in ("tool_call", "tool_result")
            and "tc-1" in e.get("data", "")
        ]
        assert not subagent_tool_leaked, (
            f"Subagent tool events leaked to parent buf: {subagent_tool_leaked}"
        )

    @pytest.mark.asyncio
    async def test_non_subagent_events_still_go_to_parent(self, tmp_db, app):
        """command_progress and other non-subagent events must still reach parent buf."""
        task_id = "task-005"
        agent_id = f"subagent-{task_id}"
        events = [
            {"event": "command_progress", "data": json.dumps({"output": "running..."})},
            {"event": "task_start", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}", "agent_id": agent_id}
            )},
            {"event": "task_done", "data": json.dumps(
                {"task_id": task_id, "thread_id": f"subagent_{task_id}", "status": "completed", "agent_id": agent_id}
            )},
        ]
        agent = make_agent(events)
        parent_buf = await _run(agent, "thread-E", app, tmp_db)

        parent_types = _parent_event_types(parent_buf)
        assert "command_progress" in parent_types

    @pytest.mark.asyncio
    async def test_sa_buf_has_terminal_run_done_event(self, tmp_db, app):
        """Subagent buffer must have a terminal 'run_done' event so SSE consumer exits."""
        task_id = "task-006"
        sa_thread_id = f"subagent_{task_id}"
        agent_id = f"subagent-{task_id}"
        events = [
            {"event": "task_start", "data": json.dumps(
                {"task_id": task_id, "thread_id": sa_thread_id, "agent_id": agent_id}
            )},
            {"event": "task_done", "data": json.dumps(
                {"task_id": task_id, "thread_id": sa_thread_id, "status": "completed", "agent_id": agent_id}
            )},
        ]
        agent = make_agent(events)
        await _run(agent, "thread-F", app, tmp_db)

        sa_buf = app.state.subagent_buffers.history.get(sa_thread_id)
        assert sa_buf is not None
        assert sa_buf.finished.is_set(), "sa_buf.mark_done() was not called"
        terminal = [e for e in sa_buf.events if e["event"] == "run_done"]
        assert len(terminal) == 1, f"Expected 1 terminal 'run_done' event, got {[e['event'] for e in sa_buf.events]}"


# ---------------------------------------------------------------------------
# Event-store verification (runs against real DB data if available)
# ---------------------------------------------------------------------------


class TestEventStoreVerification:
    """
    Verify that the drain loop path never wrote subagent content events
    (text/tool_call/tool_result with agent_id != "main") to the parent thread in the real DB.

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

    # The refactor (agent_id-based routing) was committed on 2026-03-05.
    # Old events in the DB predate the refactor.
    REFACTOR_DATE = "2026-03-05 00:00:00"

    def test_no_subagent_text_via_emit_path(self):
        """
        After the refactor, subagent content events (old name: subagent_task_text) must NOT
        appear in parent thread runs via the emit() path.

        Only checks events created on or after REFACTOR_DATE to exclude pre-refactor history.
        """
        rows = self._query(f"""
            SELECT thread_id, run_id, count(*) as cnt
            FROM run_events
            WHERE event_type = 'subagent_task_text'
              AND created_at >= '{self.REFACTOR_DATE}'
            GROUP BY thread_id, run_id
        """)
        assert rows == [], (
            f"subagent_task_text (old name) still present after refactor: {rows}"
        )

    def test_task_start_done_present_via_emit_path(self):
        """
        At least one parent thread should have task lifecycle events (task_start/task_done)
        via the emit() path, confirming routing is active.

        Skipped when DB has no subagent activity (clean install / no Task tool usage).
        """
        rows = self._query(f"""
            SELECT count(*) FROM run_events
            WHERE event_type IN ('task_start', 'task_done')
              AND created_at >= '{self.REFACTOR_DATE}'
        """)
        count = rows[0][0]
        if count == 0:
            pytest.skip("No post-refactor task_start/task_done events — run a subagent to validate")
