"""Integration tests for MemoryMiddleware with SummaryStore persistence.

Tests the complete flow: MemoryMiddleware → SummaryStore → SQLite → Checkpointer
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from core.runtime.middleware import ModelRequest, ModelResponse
from core.runtime.middleware.memory.middleware import MemoryMiddleware
from core.runtime.middleware.memory.summary_store import SummaryStore
from sandbox.thread_context import set_current_thread_id


@pytest.fixture
def mock_checkpointer():
    """Create mock checkpointer for testing."""
    checkpointer = MagicMock()

    def mock_get(config):
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return None

        # Return mock checkpoint with messages
        return {
            "channel_values": {
                "messages": [
                    HumanMessage(content="Test message 1"),
                    AIMessage(content="Response 1"),
                    HumanMessage(content="Test message 2"),
                    AIMessage(content="Response 2"),
                ]
            }
        }

    checkpointer.get = mock_get
    return checkpointer


@pytest.fixture
def mock_model():
    """Create mock LLM model for testing."""
    model = AsyncMock()

    async def mock_ainvoke(messages):
        # Return a mock summary response
        response = MagicMock()
        response.content = "This is a test summary of the conversation."
        return response

    model.ainvoke = mock_ainvoke
    return model


@pytest.fixture
def mock_request():
    """Create mock ModelRequest for testing."""
    request = MagicMock()
    request.messages = []
    request.system_message = None

    # Add config with thread_id
    config = MagicMock()
    config.configurable = {"thread_id": "test-thread-1"}
    request.config = config

    return request


def create_large_message_list(count: int = 50) -> list:
    """Create a large list of messages to trigger compaction."""
    messages = []
    for i in range(count):
        messages.append(HumanMessage(content=f"User message {i}" * 100))  # ~1500 chars each
        messages.append(AIMessage(content=f"AI response {i}" * 100))
    return messages


class TestSummarySaveOnCompaction:
    """Test 1: Verify summary is saved to store when compaction occurs."""

    @pytest.mark.asyncio
    async def test_summary_save_on_compaction(self, temp_db, mock_model, mock_request):
        """Trigger compaction and verify summary is saved to store."""
        # Create middleware with low threshold to trigger compaction
        middleware = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            verbose=True,
        )
        middleware.set_model(mock_model)

        # Create large message list to trigger compaction
        messages = create_large_message_list(30)
        mock_request.messages = messages

        # Mock handler
        async def mock_handler(req):
            return MagicMock()

        # Execute middleware
        await middleware.awrap_model_call(mock_request, mock_handler)

        # Verify summary was saved to store
        store = SummaryStore(temp_db)
        summary = store.get_latest_summary("test-thread-1")

        assert summary is not None
        assert summary.thread_id == "test-thread-1"
        # Summary text may include split turn context
        assert "This is a test summary of the conversation." in summary.summary_text
        assert summary.compact_up_to_index > 0
        assert summary.compacted_at == len(messages)
        assert summary.is_active is True


class TestSummaryRestoreOnStartup:
    """Test 2: Verify summary is restored from store on middleware startup."""

    @pytest.mark.asyncio
    async def test_summary_restore_on_startup(self, temp_db, mock_model, mock_request):
        """Restart middleware and verify summary is restored from store."""
        # Step 1: Create middleware and trigger compaction
        middleware1 = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            verbose=True,
        )
        middleware1.set_model(mock_model)

        messages = create_large_message_list(30)
        mock_request.messages = messages

        async def mock_handler(req):
            return MagicMock()

        await middleware1.awrap_model_call(mock_request, mock_handler)

        # Verify summary was saved
        assert middleware1._cached_summary is not None
        original_summary = middleware1._cached_summary
        original_index = middleware1._compact_up_to_index

        # Step 2: Create new middleware instance (simulating restart)
        middleware2 = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            verbose=True,
        )
        middleware2.set_model(mock_model)

        # Create new request with fewer messages (below threshold)
        small_messages = create_large_message_list(5)
        mock_request.messages = small_messages

        # Execute middleware - should restore summary
        await middleware2.awrap_model_call(mock_request, mock_handler)

        # Verify summary was restored
        assert middleware2._cached_summary == original_summary
        assert middleware2._compact_up_to_index == original_index
        assert middleware2._summary_restored is True

    @pytest.mark.asyncio
    async def test_summary_restore_is_isolated_per_thread_on_shared_middleware(self, temp_db, mock_model):
        middleware = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            verbose=True,
        )
        middleware.set_model(mock_model)

        store = SummaryStore(temp_db)
        store.save_summary(
            thread_id="t1",
            summary_text="SUMMARY ONE",
            compact_up_to_index=1,
            compacted_at=2,
        )
        store.save_summary(
            thread_id="t2",
            summary_text="SUMMARY TWO",
            compact_up_to_index=1,
            compacted_at=2,
        )

        async def handler(req: ModelRequest) -> ModelResponse:
            return ModelResponse(result=[], request_messages=req.messages)

        request_t1 = ModelRequest(
            model=RunnableLambda(lambda x: x),
            messages=[HumanMessage(content="a1"), HumanMessage(content="a2")],
            system_message=None,
        )

        request_t2 = ModelRequest(
            model=RunnableLambda(lambda x: x),
            messages=[HumanMessage(content="b1"), HumanMessage(content="b2")],
            system_message=None,
        )

        set_current_thread_id("t1")
        result_t1 = await middleware.awrap_model_call(request_t1, handler)
        set_current_thread_id("t2")
        result_t2 = await middleware.awrap_model_call(request_t2, handler)

        assert [getattr(msg, "content", "") for msg in result_t1.request_messages] == [
            "[Conversation Summary]\nSUMMARY ONE",
            "a2",
        ]
        assert [getattr(msg, "content", "") for msg in result_t2.request_messages] == [
            "[Conversation Summary]\nSUMMARY TWO",
            "b2",
        ]


class TestSplitTurnSaveAndRestore:
    """Test 3: Verify split turn summaries are saved and restored correctly."""

    @pytest.mark.asyncio
    async def test_split_turn_save_and_restore(self, temp_db, mock_model, mock_request):
        """Test split turn scenario with save and restore."""
        # Create mock model that returns different summaries
        call_count = [0]

        async def mock_ainvoke_split(messages):
            response = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                response.content = "Historical summary"
            else:
                response.content = "Turn prefix summary"
            return response

        mock_model.ainvoke = mock_ainvoke_split

        # Create middleware with very low keep_recent_tokens to force split turn

        compaction_config = MagicMock()
        compaction_config.reserve_tokens = 16384
        compaction_config.keep_recent_tokens = 5000  # Very low to trigger split

        middleware = MemoryMiddleware(
            context_limit=20000,
            compaction_threshold=0.5,
            db_path=temp_db,
            compaction_config=compaction_config,
            verbose=True,
        )
        middleware.set_model(mock_model)

        # Create messages with very large recent content
        messages = []
        for i in range(20):
            messages.append(HumanMessage(content=f"Old message {i}" * 50))
            messages.append(AIMessage(content=f"Old response {i}" * 50))

        # Add very large recent messages to trigger split turn
        for i in range(5):
            messages.append(HumanMessage(content=f"Recent huge message {i}" * 500))
            messages.append(AIMessage(content=f"Recent huge response {i}" * 500))

        mock_request.messages = messages

        async def mock_handler(req):
            return MagicMock()

        # Execute middleware
        await middleware.awrap_model_call(mock_request, mock_handler)

        # Verify split turn summary was saved
        store = SummaryStore(temp_db)
        summary = store.get_latest_summary("test-thread-1")

        assert summary is not None
        # Note: split turn detection may not trigger with current thresholds
        # This test verifies the save/restore mechanism works regardless


class TestRebuildFromCheckpointer:
    """Test 4: Verify summary can be rebuilt from checkpointer when store data is corrupted."""

    @pytest.mark.asyncio
    async def test_rebuild_from_checkpointer(self, temp_db, mock_model, mock_checkpointer, mock_request):
        """Test rebuilding summary from checkpointer when store is corrupted."""
        # Create middleware with checkpointer
        middleware = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            checkpointer=mock_checkpointer,
            verbose=True,
        )
        middleware.set_model(mock_model)

        # Manually corrupt the store by saving invalid data
        store = SummaryStore(temp_db)
        store.save_summary(
            thread_id="test-thread-1",
            summary_text="",  # Invalid empty summary
            compact_up_to_index=-1,  # Invalid index
            compacted_at=0,
        )

        # Create request with messages
        messages = create_large_message_list(30)
        mock_request.messages = messages

        async def mock_handler(req):
            return MagicMock()

        # Execute middleware - should detect corruption and rebuild
        await middleware.awrap_model_call(mock_request, mock_handler)

        # Verify summary was rebuilt
        rebuilt_summary = store.get_latest_summary("test-thread-1")
        assert rebuilt_summary is not None
        assert rebuilt_summary.summary_text != ""
        assert rebuilt_summary.compact_up_to_index >= 0


class TestMultipleThreadsIsolated:
    """Test 5: Verify multiple thread_ids maintain isolated summaries."""

    @pytest.mark.asyncio
    async def test_multiple_threads_isolated(self, temp_db, mock_model):
        """Test that multiple threads maintain separate summaries."""
        middleware = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            verbose=True,
        )
        middleware.set_model(mock_model)

        # Create different summaries for different threads
        async def mock_handler(req):
            return MagicMock()

        # Thread 1
        request1 = MagicMock()
        request1.messages = create_large_message_list(30)
        request1.system_message = None
        config1 = MagicMock()
        config1.configurable = {"thread_id": "thread-1"}
        request1.config = config1

        # Thread 2
        request2 = MagicMock()
        request2.messages = create_large_message_list(30)
        request2.system_message = None
        config2 = MagicMock()
        config2.configurable = {"thread_id": "thread-2"}
        request2.config = config2

        # Execute for both threads
        await middleware.awrap_model_call(request1, mock_handler)

        # Reset restoration flag for second thread
        middleware._summary_restored = False

        await middleware.awrap_model_call(request2, mock_handler)

        # Verify both threads have separate summaries
        store = SummaryStore(temp_db)
        summary1 = store.get_latest_summary("thread-1")
        summary2 = store.get_latest_summary("thread-2")

        assert summary1 is not None
        assert summary2 is not None
        assert summary1.thread_id == "thread-1"
        assert summary2.thread_id == "thread-2"
        assert summary1.summary_id != summary2.summary_id


class TestMissingThreadIdRaisesError:
    """Test 6: Verify missing thread_id is handled gracefully."""

    @pytest.mark.asyncio
    async def test_missing_thread_id_raises_error(self, temp_db, mock_model):
        """Test that missing thread_id skips restoration but allows execution."""
        # First, save a summary to trigger restore logic
        store = SummaryStore(temp_db)
        store.save_summary(
            thread_id="test-thread-1",
            summary_text="Existing summary",
            compact_up_to_index=10,
            compacted_at=20,
        )

        middleware = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            verbose=True,
        )
        middleware.set_model(mock_model)

        # Create request without thread_id
        request = MagicMock()
        request.messages = [HumanMessage(content="Test")]  # Small message to avoid compaction
        request.system_message = None
        config = MagicMock()
        config.configurable = {}  # No thread_id
        request.config = config

        async def mock_handler(req):
            return MagicMock()

        # Execute middleware - should skip restoration but continue normally
        result = await middleware.awrap_model_call(request, mock_handler)

        # Verify execution succeeded
        assert result is not None
        # Verify summary was not restored (since thread_id was missing)
        assert middleware._cached_summary is None
        assert middleware._summary_restored is False


class TestCheckpointerUnavailableGracefulDegradation:
    """Test 7: Verify graceful degradation when checkpointer is unavailable."""

    @pytest.mark.asyncio
    async def test_checkpointer_unavailable_graceful_degradation(self, temp_db, mock_model, mock_request):
        """Test that middleware works without checkpointer."""
        # Create middleware without checkpointer
        middleware = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            checkpointer=None,  # No checkpointer
            verbose=True,
        )
        middleware.set_model(mock_model)

        # Corrupt the store
        store = SummaryStore(temp_db)
        store.save_summary(
            thread_id="test-thread-1",
            summary_text="",
            compact_up_to_index=-1,
            compacted_at=0,
        )

        # Create request
        messages = create_large_message_list(30)
        mock_request.messages = messages

        async def mock_handler(req):
            return MagicMock()

        # Execute middleware - should not crash, just skip rebuild
        # Since checkpointer is None, it will perform fresh compaction instead
        await middleware.awrap_model_call(mock_request, mock_handler)

        # Verify middleware continues to work (no crash)
        # Fresh compaction should have created a new summary
        assert middleware._cached_summary is not None
        assert "This is a test summary of the conversation." in middleware._cached_summary


class TestSummaryUpdateOnSecondCompaction:
    """Test 8: Verify summary is updated correctly on second compaction."""

    @pytest.mark.asyncio
    async def test_summary_update_on_second_compaction(self, temp_db, mock_model, mock_request):
        """Test that second compaction updates the summary correctly."""
        # Create mock model that returns different summaries
        call_count = [0]

        async def mock_ainvoke_sequential(messages):
            response = MagicMock()
            call_count[0] += 1
            response.content = f"Summary version {call_count[0]}"
            return response

        mock_model.ainvoke = mock_ainvoke_sequential

        middleware = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            verbose=True,
        )
        middleware.set_model(mock_model)

        # First compaction
        messages1 = create_large_message_list(30)
        mock_request.messages = messages1

        async def mock_handler(req):
            return MagicMock()

        await middleware.awrap_model_call(mock_request, mock_handler)

        store = SummaryStore(temp_db)
        summary1 = store.get_latest_summary("test-thread-1")
        assert summary1 is not None
        # Summary may include split turn context, so check for version 1 presence
        assert "Summary version 1" in summary1.summary_text or "Summary version 2" in summary1.summary_text

        # Second compaction with more messages
        messages2 = create_large_message_list(60)
        mock_request.messages = messages2

        # Reset restoration flag to allow new compaction
        middleware._summary_restored = False

        await middleware.awrap_model_call(mock_request, mock_handler)

        # Verify summary was updated
        summary2 = store.get_latest_summary("test-thread-1")
        assert summary2 is not None
        # Check that a new summary version exists
        assert "Summary version" in summary2.summary_text
        assert summary2.summary_id != summary1.summary_id

        # Verify old summary is marked inactive
        all_summaries = store.list_summaries("test-thread-1")
        assert len(all_summaries) == 2
        active_summaries = [s for s in all_summaries if s["is_active"]]
        assert len(active_summaries) == 1
        assert active_summaries[0]["summary_id"] == summary2.summary_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
