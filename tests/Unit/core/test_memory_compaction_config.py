from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from core.runtime.middleware.memory.middleware import MemoryMiddleware


def _large_messages() -> list:
    return [
        HumanMessage(content="user " * 1200),
        AIMessage(content="assistant " * 1200),
        HumanMessage(content="continue " * 1200),
    ]


def _mock_request(messages: list):
    request = MagicMock()
    request.messages = messages
    request.system_message = None
    config = MagicMock()
    config.configurable = {"thread_id": "thread-compact-trigger"}
    request.config = config
    request.override = lambda messages: SimpleNamespace(messages=messages, prepared_request=None)
    return request


def _mock_model():
    model = MagicMock()
    model.summary_calls = 0

    async def _ainvoke(_messages):
        model.summary_calls += 1
        response = MagicMock()
        response.content = "compact summary"
        return response

    model.ainvoke = _ainvoke
    model.bind.return_value = model
    return model


def _mock_empty_summary_model():
    model = MagicMock()
    model.summary_calls = 0

    async def _ainvoke(_messages):
        model.summary_calls += 1
        response = MagicMock()
        response.content = ""
        return response

    model.ainvoke = _ainvoke
    model.bind.return_value = model
    return model


@pytest.mark.asyncio
async def test_explicit_trigger_tokens_controls_compaction_independent_of_context_limit(tmp_path):
    middleware = MemoryMiddleware(
        context_limit=1_000_000,
        compaction_threshold=0.7,
        compaction_config=SimpleNamespace(
            reserve_tokens=0,
            keep_recent_tokens=1,
            trigger_tokens=1000,
        ),
        db_path=tmp_path / "summary.db",
    )
    model = _mock_model()
    middleware.set_model(model)
    handler_messages = None

    async def _handler(req):
        nonlocal handler_messages
        handler_messages = req.messages
        return MagicMock()

    await middleware.awrap_model_call(_mock_request(_large_messages()), _handler)

    assert model.summary_calls == 1
    assert middleware.compact_boundary_index > 0
    assert handler_messages is not None
    assert isinstance(handler_messages[-1], HumanMessage)
    assert handler_messages[-1].content.startswith("continue ")


@pytest.mark.asyncio
async def test_empty_compaction_summary_does_not_advance_boundary_or_save_notice(tmp_path):
    middleware = MemoryMiddleware(
        context_limit=1_000_000,
        compaction_threshold=0.7,
        compaction_config=SimpleNamespace(
            reserve_tokens=0,
            keep_recent_tokens=1,
            trigger_tokens=1000,
        ),
        db_path=tmp_path / "summary.db",
    )
    model = _mock_empty_summary_model()
    middleware.set_model(model)
    handler_messages = None

    async def _handler(req):
        nonlocal handler_messages
        handler_messages = req.messages
        return MagicMock()

    await middleware.awrap_model_call(_mock_request(_large_messages()), _handler)

    assert model.summary_calls == 1
    assert middleware.compact_boundary_index == 0
    assert middleware.consume_pending_notices() == []
    assert middleware.summary_store is not None
    assert middleware.summary_store.list_summaries("thread-compact-trigger") == []
    assert handler_messages == _large_messages()
