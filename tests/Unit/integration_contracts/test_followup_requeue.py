from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.runtime.middleware.queue.manager import MessageQueueManager


@pytest.fixture()
def queue_manager(tmp_path):
    qm = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    yield qm


@pytest.fixture()
def mock_app(queue_manager):
    state = SimpleNamespace(
        queue_manager=queue_manager,
        thread_event_buffers={},
        thread_tasks={},
    )
    return SimpleNamespace(state=state)


@pytest.fixture()
def mock_agent():
    runtime = MagicMock()
    runtime.transition.return_value = True
    runtime._activity_sink = None
    return SimpleNamespace(runtime=runtime)


@pytest.mark.asyncio
class TestConsumeFollowupQueue:
    async def test_no_followup_does_nothing(self, mock_agent, mock_app):
        from backend.threads.streaming import _consume_followup_queue

        await _consume_followup_queue(mock_agent, "thread-1", mock_app)
        assert mock_app.state.queue_manager.dequeue("thread-1") is None
        mock_agent.runtime.transition.assert_not_called()

    async def test_successful_followup_consumes_message(self, mock_agent, mock_app, queue_manager):
        queue_manager.enqueue("do something", "thread-1")
        from backend.threads.streaming import _consume_followup_queue

        with patch("backend.threads.streaming.start_agent_run") as mock_start:
            mock_start.return_value = "run-123"

            await _consume_followup_queue(mock_agent, "thread-1", mock_app)

            mock_start.assert_called_once_with(
                mock_agent,
                "thread-1",
                "do something",
                mock_app,
                message_metadata={
                    "source": "system",
                    "notification_type": "steer",
                    "sender_name": None,
                    "sender_avatar_url": None,
                    "is_steer": False,
                },
            )
        assert queue_manager.dequeue("thread-1") is None

    async def test_exception_re_enqueues_message(self, mock_agent, mock_app, queue_manager):
        queue_manager.enqueue("important followup", "thread-1")
        from backend.threads.streaming import _consume_followup_queue

        with patch("backend.threads.streaming.start_agent_run", side_effect=RuntimeError("boom")):
            await _consume_followup_queue(mock_agent, "thread-1", mock_app)

        item = queue_manager.dequeue("thread-1")
        assert item is not None
        assert item.content == "important followup"

    async def test_transition_failure_skips_start(self, mock_agent, mock_app, queue_manager):
        queue_manager.enqueue("wont run", "thread-1")
        mock_agent.runtime.transition.return_value = False
        from backend.threads.streaming import _consume_followup_queue

        with patch("backend.threads.streaming.start_agent_run") as mock_start:
            await _consume_followup_queue(mock_agent, "thread-1", mock_app)
            mock_start.assert_not_called()

        item = queue_manager.dequeue("thread-1")
        assert item is not None
        assert item.content == "wont run"
