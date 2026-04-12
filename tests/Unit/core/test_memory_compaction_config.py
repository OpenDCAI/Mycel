from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from core.runtime.middleware.memory.middleware import MemoryMiddleware
from core.runtime.middleware.memory.summary_store import SummaryStore


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
    return request


def _mock_model():
    model = MagicMock()

    async def _ainvoke(_messages):
        response = MagicMock()
        response.content = "compact summary"
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
            keep_recent_tokens=500,
            trigger_tokens=1000,
        ),
        db_path=tmp_path / "summary.db",
    )
    middleware.set_model(_mock_model())

    async def _handler(req):
        return MagicMock()

    await middleware.awrap_model_call(_mock_request(_large_messages()), _handler)

    summary = SummaryStore(tmp_path / "summary.db").get_latest_summary("thread-compact-trigger")
    assert summary is not None
    assert summary.summary_text == "compact summary"
