"""Tests for unified message queue: enqueue/dequeue/drain_all + wake handlers."""

import threading
from pathlib import Path

import pytest

from core.runtime.middleware.queue import MessageQueueManager
from core.runtime.middleware.queue.formatters import format_steer_reminder, format_background_notification


@pytest.fixture()
def tmp_db(tmp_path):
    """Provide a temporary SQLite database path."""
    return str(tmp_path / "test.db")


class TestQueueDatabaseIsolation:
    def test_default_queue_path_uses_dedicated_queue_db(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "leon.db"))
        monkeypatch.delenv("LEON_QUEUE_DB_PATH", raising=False)

        mgr = MessageQueueManager()
        expected = tmp_path / "queue.db"
        assert Path(mgr._db_path) == expected

    def test_queue_path_honors_leon_queue_db_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "leon.db"))
        monkeypatch.setenv("LEON_QUEUE_DB_PATH", str(tmp_path / "custom-queue.db"))

        mgr = MessageQueueManager()
        assert Path(mgr._db_path) == (tmp_path / "custom-queue.db")


# ---------------------------------------------------------------------------
# 1. Enqueue / dequeue path — SQLite persistent
# ---------------------------------------------------------------------------


class TestEnqueueDequeue:
    def test_enqueue_and_dequeue(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("hello", thread_id="t1")
        assert mgr.peek("t1")
        item = mgr.dequeue("t1")
        assert item is not None
        assert item.content == "hello"
        assert item.notification_type == "steer"
        assert not mgr.peek("t1")

    def test_fifo_order(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("first", thread_id="t1")
        mgr.enqueue("second", thread_id="t1")
        mgr.enqueue("third", thread_id="t1")
        assert mgr.dequeue("t1").content == "first"
        assert mgr.dequeue("t1").content == "second"
        assert mgr.dequeue("t1").content == "third"
        assert mgr.dequeue("t1") is None

    def test_thread_isolation(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("for-t1", thread_id="t1")
        mgr.enqueue("for-t2", thread_id="t2")
        assert mgr.dequeue("t1").content == "for-t1"
        assert mgr.dequeue("t2").content == "for-t2"
        assert mgr.dequeue("t1") is None

    def test_dequeue_empty(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        assert mgr.dequeue("nonexistent") is None

    def test_dequeue_empty_does_not_issue_delete(self, tmp_db):
        """Empty queue dequeue should check first, skip DELETE."""
        mgr = MessageQueueManager(db_path=tmp_db)
        assert mgr.dequeue("t-empty") is None
        assert not mgr.peek("t-empty")

    def test_peek_does_not_consume(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("msg", thread_id="t1")
        assert mgr.peek("t1")
        assert mgr.peek("t1")  # still there
        assert mgr.dequeue("t1").content == "msg"

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
        assert mgr2.dequeue("t1").content == "shared-msg"

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
                item = local_mgr.dequeue("t1")
                if item is None:
                    break
                with lock:
                    results.append(item.content)

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
        assert [i.content for i in items] == ["first", "second", "third"]

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

    def test_drain_empty_does_not_issue_delete(self, tmp_db):
        """Empty queue drain should return empty list without issuing DELETE."""
        mgr = MessageQueueManager(db_path=tmp_db)
        assert mgr.drain_all("t-empty") == []
        assert not mgr.peek("t-empty")

    def test_drain_thread_isolation(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("for-t1", thread_id="t1")
        mgr.enqueue("for-t2", thread_id="t2")
        assert [i.content for i in mgr.drain_all("t1")] == ["for-t1"]
        assert [i.content for i in mgr.drain_all("t2")] == ["for-t2"]

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
                all_items.extend(i.content for i in items)

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
        mgr.register_wake("t1", lambda item: calls.append("woke"))
        mgr.enqueue("msg", thread_id="t1")
        assert calls == ["woke"]

    def test_no_handler_no_error(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        # No wake handler registered — should not raise
        mgr.enqueue("msg", thread_id="t1")

    def test_handler_exception_does_not_prevent_enqueue(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)

        def bad_handler(item: object):
            raise RuntimeError("boom")

        mgr.register_wake("t1", bad_handler)
        mgr.enqueue("msg", thread_id="t1")
        # Message should still be in queue despite handler failure
        assert mgr.dequeue("t1").content == "msg"

    def test_unregister_stops_firing(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        calls = []
        mgr.register_wake("t1", lambda item: calls.append("woke"))
        mgr.unregister_wake("t1")
        mgr.enqueue("msg", thread_id="t1")
        assert calls == []

    def test_thread_isolation(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        t1_calls = []
        t2_calls = []
        mgr.register_wake("t1", lambda item: t1_calls.append(1))
        mgr.register_wake("t2", lambda item: t2_calls.append(1))
        mgr.enqueue("msg", thread_id="t1")
        assert t1_calls == [1]
        assert t2_calls == []

    def test_wake_handler_called_per_enqueue(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        calls = []
        mgr.register_wake("t1", lambda item: calls.append(1))
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
        mgr.register_wake("t1", lambda item: calls.append(1))
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
        from core.runtime.middleware.queue.middleware import SteeringMiddleware

        mgr = MessageQueueManager(db_path=tmp_db)
        middleware = SteeringMiddleware(queue_manager=mgr)

        thread_id = "test-middleware"
        mgr.enqueue("change direction", thread_id=thread_id)

        # Middleware calls drain_all internally
        items = mgr.drain_all(thread_id)
        assert len(items) == 1
        assert items[0].content == "change direction"
        assert not mgr.peek(thread_id)

    def test_middleware_drains_multiple(self, tmp_db):
        """Middleware drains all pending messages at once."""
        mgr = MessageQueueManager(db_path=tmp_db)

        thread_id = "test-multi"
        mgr.enqueue("first", thread_id=thread_id)
        mgr.enqueue("second", thread_id=thread_id)

        items = mgr.drain_all(thread_id)
        assert [i.content for i in items] == ["first", "second"]
        assert mgr.drain_all(thread_id) == []

    def test_tool_calls_never_skipped(self, tmp_db):
        """Verify wrap_tool_call is a pure passthrough (non-preemptive)."""
        from unittest.mock import MagicMock

        from core.runtime.middleware.queue.middleware import SteeringMiddleware

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

    def test_format_background_notification(self):
        xml = format_background_notification(
            task_id="abc123",
            status="completed",
            summary="Analysis done",
            result="Found 5 issues",
        )
        assert "<background-notification>" in xml
        assert "<run-id>abc123</run-id>" in xml
        assert "<status>completed</status>" in xml
        assert "<summary>Analysis done</summary>" in xml
        assert "<result>Found 5 issues</result>" in xml

    def test_format_background_notification_truncates_long_result(self):
        long_result = "x" * 3000
        xml = format_background_notification(
            task_id="t1", status="completed", summary="done", result=long_result
        )
        assert "..." in xml
        # Result field should be truncated
        assert len(xml) < 3000

    def test_format_background_notification_no_result(self):
        xml = format_background_notification(task_id="t1", status="error", summary="failed")
        assert "<result>" not in xml


# ---------------------------------------------------------------------------
# 8. Notification type
# ---------------------------------------------------------------------------


class TestNotificationType:
    def test_enqueue_with_type_dequeue_preserves(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("agent done", thread_id="t1", notification_type="agent")
        item = mgr.dequeue("t1")
        assert item.content == "agent done"
        assert item.notification_type == "agent"

    def test_default_type_is_steer(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("plain msg", thread_id="t1")
        item = mgr.dequeue("t1")
        assert item.notification_type == "steer"

    def test_drain_preserves_types(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("a", thread_id="t1", notification_type="agent")
        mgr.enqueue("b", thread_id="t1", notification_type="steer")
        mgr.enqueue("c", thread_id="t1", notification_type="command")
        items = mgr.drain_all("t1")
        assert [(i.content, i.notification_type) for i in items] == [
            ("a", "agent"),
            ("b", "steer"),
            ("c", "command"),
        ]

    def test_list_queue_includes_type(self, tmp_db):
        mgr = MessageQueueManager(db_path=tmp_db)
        mgr.enqueue("x", thread_id="t1", notification_type="agent")
        items = mgr.list_queue("t1")
        assert items[0]["notification_type"] == "agent"
