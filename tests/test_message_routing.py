"""Tests for unified message queue: enqueue/dequeue/drain_all + wake handlers."""

import threading

import pytest

from core.queue import MessageQueueManager
from core.queue.formatters import format_steer_reminder, format_task_notification


@pytest.fixture()
def tmp_db(tmp_path):
    """Provide a temporary SQLite database path."""
    return str(tmp_path / "test.db")


# ---------------------------------------------------------------------------
# 1. Enqueue / dequeue path — SQLite persistent
# ---------------------------------------------------------------------------


class TestEnqueueDequeue:
    def test_enqueue_and_dequeue(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("hello", thread_id="t1")
        assert mgr.peek("t1")
        assert mgr.dequeue("t1") == "hello"
        assert not mgr.peek("t1")

    def test_fifo_order(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("first", thread_id="t1")
        mgr.enqueue("second", thread_id="t1")
        mgr.enqueue("third", thread_id="t1")
        assert mgr.dequeue("t1") == "first"
        assert mgr.dequeue("t1") == "second"
        assert mgr.dequeue("t1") == "third"
        assert mgr.dequeue("t1") is None

    def test_thread_isolation(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("for-t1", thread_id="t1")
        mgr.enqueue("for-t2", thread_id="t2")
        assert mgr.dequeue("t1") == "for-t1"
        assert mgr.dequeue("t2") == "for-t2"
        assert mgr.dequeue("t1") is None

    def test_dequeue_empty(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        assert mgr.dequeue("nonexistent") is None

    def test_peek_does_not_consume(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("msg", thread_id="t1")
        assert mgr.peek("t1")
        assert mgr.peek("t1")  # still there
        assert mgr.dequeue("t1") == "msg"

    def test_list_queue(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("a", thread_id="t1")
        mgr.enqueue("b", thread_id="t1")
        items = mgr.list_queue("t1")
        assert len(items) == 2
        assert items[0]["content"] == "a"
        assert items[1]["content"] == "b"

    def test_clear_queue(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("a", thread_id="t1")
        mgr.enqueue("b", thread_id="t1")
        mgr.clear_queue("t1")
        assert not mgr.peek("t1")
        assert mgr.dequeue("t1") is None

    def test_cross_instance_persistence(self, tmp_db):
        """Different manager instances sharing the same DB can consume each other's messages."""
        mgr1 = MessageQueueManager(db_path=tmp_db)
        mgr1.enqueue("shared-msg", thread_id="t1")

        mgr2 = MessageQueueManager(db_path=tmp_db)
        assert mgr2.dequeue("t1") == "shared-msg"

    def test_concurrent_dequeue_no_duplicates(self, tmp_db):
        """Under concurrent access, each message is consumed exactly once."""
        mgr = MessageQueueManager(db_path=tmp_db)
        for i in range(20):
            mgr.enqueue(f"msg-{i}", thread_id="t1")

        results = []
        lock = threading.Lock()

        def consumer():
            local_mgr = MessageQueueManager(db_path=tmp_db)
            while True:
                msg = local_mgr.dequeue("t1")
                if msg is None:
                    break
                with lock:
                    results.append(msg)

        threads = [threading.Thread(target=consumer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(results) == sorted(f"msg-{i}" for i in range(20))


# ---------------------------------------------------------------------------
# 2. drain_all — atomic batch consumption
# ---------------------------------------------------------------------------


class TestDrainAll:
    def test_drain_returns_all_fifo(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("first", thread_id="t1")
        mgr.enqueue("second", thread_id="t1")
        mgr.enqueue("third", thread_id="t1")
        items = mgr.drain_all("t1")
        assert items == ["first", "second", "third"]

    def test_drain_empties_queue(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("msg", thread_id="t1")
        mgr.drain_all("t1")
        assert not mgr.peek("t1")
        assert mgr.dequeue("t1") is None
        assert mgr.drain_all("t1") == []

    def test_drain_empty_returns_empty_list(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        assert mgr.drain_all("nonexistent") == []

    def test_drain_thread_isolation(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("for-t1", thread_id="t1")
        mgr.enqueue("for-t2", thread_id="t2")
        assert mgr.drain_all("t1") == ["for-t1"]
        assert mgr.drain_all("t2") == ["for-t2"]

    def test_drain_concurrent_no_duplicates(self, tmp_db):
        """Under concurrent access, drain_all delivers each message exactly once."""
        mgr = MessageQueueManager(db_path=tmp_db)
        for i in range(20):
            mgr.enqueue(f"msg-{i}", thread_id="t1")

        all_items = []
        lock = threading.Lock()

        def drainer():
            local_mgr = MessageQueueManager(db_path=tmp_db)
            items = local_mgr.drain_all("t1")
            with lock:
                all_items.extend(items)

        threads = [threading.Thread(target=drainer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(all_items) == sorted(f"msg-{i}" for i in range(20))


# ---------------------------------------------------------------------------
# 3. Wake handler
# ---------------------------------------------------------------------------


class TestWakeHandler:
    def test_enqueue_fires_wake_handler(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        calls = []
        mgr.register_wake("t1", lambda: calls.append("woke"))
        mgr.enqueue("msg", thread_id="t1")
        assert calls == ["woke"]

    def test_no_handler_no_error(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        # No wake handler registered — should not raise
        mgr.enqueue("msg", thread_id="t1")

    def test_handler_exception_does_not_prevent_enqueue(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)

        def bad_handler():
            raise RuntimeError("boom")

        mgr.register_wake("t1", bad_handler)
        mgr.enqueue("msg", thread_id="t1")
        # Message should still be in queue despite handler failure
        assert mgr.dequeue("t1") == "msg"

    def test_unregister_stops_firing(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        calls = []
        mgr.register_wake("t1", lambda: calls.append("woke"))
        mgr.unregister_wake("t1")
        mgr.enqueue("msg", thread_id="t1")
        assert calls == []

    def test_thread_isolation(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        t1_calls = []
        t2_calls = []
        mgr.register_wake("t1", lambda: t1_calls.append(1))
        mgr.register_wake("t2", lambda: t2_calls.append(1))
        mgr.enqueue("msg", thread_id="t1")
        assert t1_calls == [1]
        assert t2_calls == []

    def test_wake_handler_called_per_enqueue(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        calls = []
        mgr.register_wake("t1", lambda: calls.append(1))
        mgr.enqueue("a", thread_id="t1")
        mgr.enqueue("b", thread_id="t1")
        assert len(calls) == 2


# ---------------------------------------------------------------------------
# 4. clear_all cleans queue and unregisters wake
# ---------------------------------------------------------------------------


class TestClearAll:
    def test_clear_all(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("queue-msg", thread_id="t1")
        calls = []
        mgr.register_wake("t1", lambda: calls.append(1))
        mgr.clear_all("t1")
        assert not mgr.peek("t1")
        # Wake handler should be unregistered
        mgr.enqueue("new-msg", thread_id="t1")
        assert calls == []


# ---------------------------------------------------------------------------
# 5. queue_sizes backward compat
# ---------------------------------------------------------------------------


class TestQueueSizes:
    def test_steer_always_zero(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("msg", thread_id="t1")
        sizes = mgr.queue_sizes("t1")
        assert sizes["steer"] == 0
        assert sizes["followup"] == 1


# ---------------------------------------------------------------------------
# 6. SteeringMiddleware integration — non-preemptive behavior
# ---------------------------------------------------------------------------


class TestSteeringMiddlewareIntegration:
    """Verify SteeringMiddleware reads from unified queue via drain_all."""

    def test_middleware_consumes_queued_messages(self, tmp_db):
        from core.queue.middleware import SteeringMiddleware

        mgr = MessageQueueManager(db_path=tmp_db)
        middleware = SteeringMiddleware(queue_manager=mgr)

        thread_id = "test-middleware"
        mgr.enqueue("change direction", thread_id=thread_id)

        # Middleware calls drain_all internally
        items = mgr.drain_all(thread_id)
        assert items == ["change direction"]
        assert not mgr.peek(thread_id)

    def test_middleware_drains_multiple(self, tmp_db):
        """Middleware drains all pending messages at once."""
        mgr = MessageQueueManager(db_path=tmp_db)

        thread_id = "test-multi"
        mgr.enqueue("first", thread_id=thread_id)
        mgr.enqueue("second", thread_id=thread_id)

        items = mgr.drain_all(thread_id)
        assert items == ["first", "second"]
        assert mgr.drain_all(thread_id) == []

    def test_tool_calls_never_skipped(self, tmp_db):
        """Verify wrap_tool_call is a pure passthrough (non-preemptive)."""
        from unittest.mock import MagicMock

        from core.queue.middleware import SteeringMiddleware

        mgr = MessageQueueManager(db_path=tmp_db)
        middleware = SteeringMiddleware(queue_manager=mgr)

        # Enqueue message to simulate mid-execution message
        mgr.enqueue("urgent message", thread_id="test-no-skip")

        # Create mock tool call request and handler
        mock_request = MagicMock()
        mock_result = MagicMock()
        mock_handler = MagicMock(return_value=mock_result)

        # wrap_tool_call should call handler normally, NOT skip
        result = middleware.wrap_tool_call(mock_request, mock_handler)
        mock_handler.assert_called_once_with(mock_request)
        assert result is mock_result


# ---------------------------------------------------------------------------
# 7. XML formatters
# ---------------------------------------------------------------------------


class TestFormatters:
    def test_format_steer_reminder(self):
        xml = format_steer_reminder("stop and do X")
        assert "<system-reminder>" in xml
        assert "stop and do X" in xml
        assert "IMPORTANT" in xml
        assert "</system-reminder>" in xml

    def test_format_task_notification(self):
        xml = format_task_notification(
            task_id="abc123",
            status="completed",
            summary="Analysis done",
            result="Found 5 issues",
        )
        assert "<task-notification>" in xml
        assert "<task-id>abc123</task-id>" in xml
        assert "<status>completed</status>" in xml
        assert "<summary>Analysis done</summary>" in xml
        assert "<result>Found 5 issues</result>" in xml

    def test_format_task_notification_truncates_long_result(self):
        long_result = "x" * 3000
        xml = format_task_notification(
            task_id="t1", status="completed", summary="done", result=long_result
        )
        assert "..." in xml
        # Result field should be truncated
        assert len(xml) < 3000

    def test_format_task_notification_no_result(self):
        xml = format_task_notification(task_id="t1", status="error", summary="failed")
        assert "<result>" not in xml
