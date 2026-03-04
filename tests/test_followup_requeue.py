"""Tests for followup queue re-enqueue logic in streaming_service.

Covers the _consume_followup_queue function:
- Normal path: dequeue + start_agent_run succeeds
- Re-enqueue on failure: message is put back when start_agent_run raises
- No followup: dequeue returns None, nothing happens
- Re-enqueue failure: logs error when enqueue also fails (message lost)
- Retry success: re-enqueued message can be processed on next attempt
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.queue.manager import MessageQueueManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def queue_manager(tmp_path):
    """Real MessageQueueManager backed by a temp SQLite DB."""
    qm = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    yield qm


@pytest.fixture()
def mock_app(queue_manager):
    """Minimal app stub with state.queue_manager and state.thread_event_buffers/thread_tasks."""
    state = SimpleNamespace(
        queue_manager=queue_manager,
        thread_event_buffers={},
        thread_tasks={},
    )
    return SimpleNamespace(state=state)


@pytest.fixture()
def mock_agent():
    """Minimal agent stub with runtime that supports transition()."""
    runtime = MagicMock()
    runtime.transition.return_value = True
    runtime._activity_sink = None
    agent = SimpleNamespace(runtime=runtime)
    return agent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConsumeFollowupQueue:
    """Tests for _consume_followup_queue re-enqueue logic."""

    def test_no_followup_does_nothing(self, mock_agent, mock_app):
        """When queue is empty, nothing happens."""
        async def _run():
            from backend.web.services.streaming_service import _consume_followup_queue
            await _consume_followup_queue(mock_agent, "thread-1", mock_app)
            # Queue is still empty
            assert mock_app.state.queue_manager.dequeue("thread-1") is None
            # Runtime transition was never called
            mock_agent.runtime.transition.assert_not_called()

        asyncio.run(_run())

    def test_successful_followup_consumes_message(self, mock_agent, mock_app, queue_manager):
        """When followup succeeds, message is consumed and not re-enqueued."""
        queue_manager.enqueue("do something", "thread-1")

        async def _run():
            from backend.web.services.streaming_service import _consume_followup_queue

            with patch("backend.web.services.streaming_service.start_agent_run") as mock_start:
                mock_buf = MagicMock()
                mock_buf.run_id = "run-123"
                mock_start.return_value = mock_buf

                await _consume_followup_queue(mock_agent, "thread-1", mock_app)

                mock_start.assert_called_once_with(
                    mock_agent, "thread-1", "do something", mock_app,
                    message_metadata={"source": "system"},
                )
            # Message was consumed, queue is empty
            assert queue_manager.dequeue("thread-1") is None

        asyncio.run(_run())

    def test_exception_re_enqueues_message(self, mock_agent, mock_app, queue_manager):
        """When start_agent_run raises, the dequeued message is re-enqueued."""
        queue_manager.enqueue("important followup", "thread-1")

        async def _run():
            from backend.web.services.streaming_service import _consume_followup_queue

            with patch("backend.web.services.streaming_service.start_agent_run",
                       side_effect=RuntimeError("boom")):
                await _consume_followup_queue(mock_agent, "thread-1", mock_app)

            # Message was re-enqueued — it should be available again
            msg = queue_manager.dequeue("thread-1")
            assert msg == "important followup"

        asyncio.run(_run())

    def test_re_enqueued_message_succeeds_on_retry(self, mock_agent, mock_app, queue_manager):
        """A re-enqueued message can be successfully processed on the next attempt."""
        queue_manager.enqueue("retry me", "thread-1")

        async def _run():
            from backend.web.services.streaming_service import _consume_followup_queue

            # First attempt: fails
            with patch("backend.web.services.streaming_service.start_agent_run",
                       side_effect=RuntimeError("temporary failure")):
                await _consume_followup_queue(mock_agent, "thread-1", mock_app)

            # Verify message was re-enqueued
            assert queue_manager.peek("thread-1") is True

            # Second attempt: succeeds
            with patch("backend.web.services.streaming_service.start_agent_run") as mock_start:
                mock_buf = MagicMock()
                mock_buf.run_id = "run-456"
                mock_start.return_value = mock_buf

                await _consume_followup_queue(mock_agent, "thread-1", mock_app)

                mock_start.assert_called_once_with(
                    mock_agent, "thread-1", "retry me", mock_app,
                    message_metadata={"source": "system"},
                )

            # Queue is now empty
            assert queue_manager.dequeue("thread-1") is None

        asyncio.run(_run())

    def test_no_re_enqueue_when_dequeue_returns_none(self, mock_agent, mock_app, queue_manager):
        """If dequeue itself raises, followup is None so re-enqueue is skipped."""
        async def _run():
            from backend.web.services.streaming_service import _consume_followup_queue

            # Make dequeue raise — followup stays None, no re-enqueue attempted
            with patch.object(queue_manager, "dequeue", side_effect=RuntimeError("db error")):
                await _consume_followup_queue(mock_agent, "thread-1", mock_app)

            # enqueue was never called for re-enqueue (followup was None)
            # Queue is still empty
            assert queue_manager.dequeue("thread-1") is None

        asyncio.run(_run())

    def test_re_enqueue_failure_logs_error(self, mock_agent, mock_app, queue_manager):
        """When both start_agent_run AND re-enqueue fail, error is logged (message lost)."""
        queue_manager.enqueue("doomed message", "thread-1")

        async def _run():
            from backend.web.services.streaming_service import _consume_followup_queue

            with patch("backend.web.services.streaming_service.start_agent_run",
                       side_effect=RuntimeError("start failed")):
                # Also make re-enqueue fail
                original_enqueue = queue_manager.enqueue
                with patch.object(queue_manager, "enqueue", side_effect=RuntimeError("enqueue failed")):
                    await _consume_followup_queue(mock_agent, "thread-1", mock_app)

            # Message is truly lost — queue is empty
            assert queue_manager.dequeue("thread-1") is None

        asyncio.run(_run())

    def test_transition_failure_skips_start(self, mock_agent, mock_app, queue_manager):
        """When runtime.transition returns False, start_agent_run is not called."""
        queue_manager.enqueue("wont run", "thread-1")
        mock_agent.runtime.transition.return_value = False

        async def _run():
            from backend.web.services.streaming_service import _consume_followup_queue

            with patch("backend.web.services.streaming_service.start_agent_run") as mock_start:
                await _consume_followup_queue(mock_agent, "thread-1", mock_app)
                mock_start.assert_not_called()

            # Message was consumed (dequeued) but not re-enqueued since no exception
            assert queue_manager.dequeue("thread-1") is None

        asyncio.run(_run())

    def test_activity_sink_called_on_success(self, mock_agent, mock_app, queue_manager):
        """When activity_sink is set, new_run event is emitted."""
        queue_manager.enqueue("with sink", "thread-1")
        sink_calls = []

        async def fake_sink(event):
            sink_calls.append(event)

        mock_agent.runtime._activity_sink = fake_sink

        async def _run():
            from backend.web.services.streaming_service import _consume_followup_queue

            with patch("backend.web.services.streaming_service.start_agent_run") as mock_start:
                mock_buf = MagicMock()
                mock_buf.run_id = "run-789"
                mock_start.return_value = mock_buf

                await _consume_followup_queue(mock_agent, "thread-1", mock_app)

            assert len(sink_calls) == 1
            assert sink_calls[0]["event"] == "new_run"
            data = json.loads(sink_calls[0]["data"])
            assert data["thread_id"] == "thread-1"
            assert data["run_id"] == "run-789"

        asyncio.run(_run())

    def test_activity_sink_error_triggers_re_enqueue(self, mock_agent, mock_app, queue_manager):
        """When activity_sink raises, the message is re-enqueued."""
        queue_manager.enqueue("sink will fail", "thread-1")

        async def broken_sink(event):
            raise RuntimeError("sink exploded")

        mock_agent.runtime._activity_sink = broken_sink

        async def _run():
            from backend.web.services.streaming_service import _consume_followup_queue

            with patch("backend.web.services.streaming_service.start_agent_run") as mock_start:
                mock_buf = MagicMock()
                mock_buf.run_id = "run-000"
                mock_start.return_value = mock_buf

                await _consume_followup_queue(mock_agent, "thread-1", mock_app)

            # Message was re-enqueued because the sink raised
            msg = queue_manager.dequeue("thread-1")
            assert msg == "sink will fail"

        asyncio.run(_run())
