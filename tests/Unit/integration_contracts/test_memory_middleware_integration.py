from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from core.runtime.middleware import ModelRequest, ModelResponse
from core.runtime.middleware.memory.middleware import MemoryMiddleware
from core.runtime.middleware.memory.summary_store import SummaryStore
from sandbox.thread_context import set_current_thread_id


@pytest.fixture
def mock_checkpointer():
    checkpointer = MagicMock()

    def mock_get(config):
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return None

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

    async def mock_aget(config):
        return mock_get(config)

    checkpointer.aget = mock_aget
    return checkpointer


@pytest.fixture
def mock_model():
    model = MagicMock()

    async def mock_ainvoke(messages):
        response = MagicMock()
        response.content = "This is a test summary of the conversation."
        return response

    model.ainvoke = mock_ainvoke
    model.bind.return_value = model
    return model


@pytest.fixture
def mock_request():
    request = MagicMock()
    request.messages = []
    request.system_message = None

    config = MagicMock()
    config.configurable = {"thread_id": "test-thread-1"}
    request.config = config

    return request


def create_large_message_list(count: int = 50) -> list:
    messages = []
    for i in range(count):
        messages.append(HumanMessage(content=f"User message {i}" * 100))  # ~1500 chars each
        messages.append(AIMessage(content=f"AI response {i}" * 100))
    return messages


class _AsyncOnlyCheckpointer:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    async def aget(self, cfg):
        return self.store.get(cfg["configurable"]["thread_id"])

    async def aput(self, cfg, checkpoint, metadata, new_versions):
        self.store[cfg["configurable"]["thread_id"]] = checkpoint


class TestSummarySaveOnCompaction:
    @pytest.mark.asyncio
    async def test_summary_save_on_compaction(self, temp_db, mock_model, mock_request):
        middleware = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            verbose=True,
        )
        middleware.set_model(mock_model)

        messages = create_large_message_list(30)
        mock_request.messages = messages

        async def mock_handler(req):
            return MagicMock()

        await middleware.awrap_model_call(mock_request, mock_handler)

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
    @pytest.mark.asyncio
    async def test_summary_restore_on_startup(self, temp_db, mock_model, mock_request):
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

        assert middleware1._cached_summary is not None
        original_summary = middleware1._cached_summary
        original_index = middleware1._compact_up_to_index

        middleware2 = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            verbose=True,
        )
        middleware2.set_model(mock_model)

        small_messages = create_large_message_list(5)
        mock_request.messages = small_messages

        await middleware2.awrap_model_call(mock_request, mock_handler)

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
        assert result_t1.request_messages is not None
        assert result_t2.request_messages is not None

        assert [getattr(msg, "content", "") for msg in result_t1.request_messages] == [
            "[Conversation Summary]\nSUMMARY ONE",
            "a2",
        ]
        assert [getattr(msg, "content", "") for msg in result_t2.request_messages] == [
            "[Conversation Summary]\nSUMMARY TWO",
            "b2",
        ]


class TestRebuildFromCheckpointer:
    @pytest.mark.asyncio
    async def test_late_bound_async_checkpointer_rebuilds_summary(self, temp_db, mock_model):
        """Late-bound async savers should be enough for rebuild; sync .get() is not required."""
        middleware = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            checkpointer=None,
            verbose=True,
        )
        middleware.set_model(mock_model)

        checkpointer = _AsyncOnlyCheckpointer()
        checkpointer.store["late-rebuild-thread"] = {
            "channel_values": {
                "messages": create_large_message_list(30),
            }
        }
        middleware.checkpointer = checkpointer

        await middleware._rebuild_summary_from_checkpointer("late-rebuild-thread")

        store = SummaryStore(temp_db)
        rebuilt_summary = store.get_latest_summary("late-rebuild-thread")
        assert rebuilt_summary is not None
        assert "This is a test summary of the conversation." in rebuilt_summary.summary_text
        assert rebuilt_summary.compact_up_to_index > 0

    @pytest.mark.asyncio
    async def test_rebuild_from_checkpointer(self, temp_db, mock_model, mock_checkpointer, mock_request):
        middleware = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            checkpointer=mock_checkpointer,
            verbose=True,
        )
        middleware.set_model(mock_model)

        store = SummaryStore(temp_db)
        store.save_summary(
            thread_id="test-thread-1",
            summary_text="",  # Invalid empty summary
            compact_up_to_index=-1,  # Invalid index
            compacted_at=0,
        )

        messages = create_large_message_list(30)
        mock_request.messages = messages

        async def mock_handler(req):
            return MagicMock()

        await middleware.awrap_model_call(mock_request, mock_handler)

        rebuilt_summary = store.get_latest_summary("test-thread-1")
        assert rebuilt_summary is not None
        assert rebuilt_summary.summary_text != ""
        assert rebuilt_summary.compact_up_to_index >= 0


class TestMultipleThreadsIsolated:
    @pytest.mark.asyncio
    async def test_multiple_threads_isolated(self, temp_db, mock_model):
        middleware = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            verbose=True,
        )
        middleware.set_model(mock_model)

        async def mock_handler(req):
            return MagicMock()

        request1 = MagicMock()
        request1.messages = create_large_message_list(30)
        request1.system_message = None
        config1 = MagicMock()
        config1.configurable = {"thread_id": "thread-1"}
        request1.config = config1

        request2 = MagicMock()
        request2.messages = create_large_message_list(30)
        request2.system_message = None
        config2 = MagicMock()
        config2.configurable = {"thread_id": "thread-2"}
        request2.config = config2

        await middleware.awrap_model_call(request1, mock_handler)

        middleware._summary_restored = False

        await middleware.awrap_model_call(request2, mock_handler)

        store = SummaryStore(temp_db)
        summary1 = store.get_latest_summary("thread-1")
        summary2 = store.get_latest_summary("thread-2")

        assert summary1 is not None
        assert summary2 is not None
        assert summary1.thread_id == "thread-1"
        assert summary2.thread_id == "thread-2"
        assert summary1.summary_id != summary2.summary_id


class TestCompactionBreakerScope:
    """Breaker should gate proactive compaction without poisoning reactive recovery."""

    @pytest.mark.asyncio
    async def test_reactive_recovery_can_bypass_and_clear_thread_breaker(self, temp_db, mock_request):
        class _EventuallyRecoveringModel:
            def __init__(self):
                self.compact_calls = 0

            async def ainvoke(self, messages):
                self.compact_calls += 1
                if self.compact_calls <= 3:
                    raise RuntimeError("compaction failed")
                response = MagicMock()
                response.content = "Recovered summary"
                return response

        model = _EventuallyRecoveringModel()
        middleware = MemoryMiddleware(
            context_limit=10000,
            compaction_threshold=0.5,
            db_path=temp_db,
            verbose=True,
        )
        middleware.set_model(model)

        messages = create_large_message_list(30)
        mock_request.messages = messages

        async def mock_handler(req):
            return ModelResponse(result=[], request_messages=req.messages)

        for _ in range(3):
            await middleware.awrap_model_call(mock_request, mock_handler)

        snapshot = middleware.snapshot_thread_state("test-thread-1")
        assert snapshot == {"failure_count": 3, "breaker_open": True}

        recovered = await middleware.compact_messages_for_recovery(
            messages,
            thread_id="test-thread-1",
        )
        assert recovered is not None
        assert getattr(recovered[0], "content", "").startswith("[Conversation Summary]\nRecovered summary")

        snapshot = middleware.snapshot_thread_state("test-thread-1")
        assert snapshot == {"failure_count": 0, "breaker_open": False}

        result = await middleware.awrap_model_call(mock_request, mock_handler)
        assert result.request_messages is not None
        assert getattr(result.request_messages[0], "content", "").startswith("[Conversation Summary]\nRecovered summary")
        assert model.compact_calls >= 5


class TestSummaryUpdateOnSecondCompaction:
    @pytest.mark.asyncio
    async def test_summary_update_on_second_compaction(self, temp_db, mock_model, mock_request):
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

        messages2 = create_large_message_list(60)
        mock_request.messages = messages2

        middleware._summary_restored = False

        await middleware.awrap_model_call(mock_request, mock_handler)

        summary2 = store.get_latest_summary("test-thread-1")
        assert summary2 is not None
        assert "Summary version" in summary2.summary_text
        assert summary2.summary_id != summary1.summary_id

        all_summaries = store.list_summaries("test-thread-1")
        assert len(all_summaries) == 2
        active_summaries = [s for s in all_summaries if s["is_active"]]
        assert len(active_summaries) == 1
        assert active_summaries[0]["summary_id"] == summary2.summary_id
