"""Backend-facing regression tests for QueryLoop caller-contract bridge."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.web.routers.threads import get_thread_history
from backend.web.services.streaming_service import _repair_incomplete_tool_calls
from core.runtime.loop import QueryLoop
from core.runtime.registry import ToolRegistry
from core.runtime.state import AppState, BootstrapConfig


class _MemoryCheckpointer:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    async def aget(self, cfg):
        return self.store.get(cfg["configurable"]["thread_id"])

    async def aput(self, cfg, checkpoint, metadata, new_versions):
        self.store[cfg["configurable"]["thread_id"]] = checkpoint


class _NoToolModel:
    def __init__(self, text: str = "done") -> None:
        self._text = text

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return AIMessage(content=self._text)


def _make_loop(*, text: str = "done", checkpointer: _MemoryCheckpointer | None = None) -> QueryLoop:
    return QueryLoop(
        model=_NoToolModel(text=text),
        system_prompt=SystemMessage(content="sys"),
        middleware=[],
        checkpointer=checkpointer,
        registry=ToolRegistry(),
        app_state=AppState(),
        runtime=None,
        bootstrap=BootstrapConfig(workspace_root=Path("/tmp"), model_name="test-model"),
        max_turns=5,
    )


@pytest.mark.asyncio
async def test_repair_incomplete_tool_calls_uses_query_loop_state_bridge():
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(checkpointer=checkpointer)
    broken_ai = AIMessage(
        content="",
        tool_calls=[{"name": "Read", "args": {"file_path": "/tmp/a.txt"}, "id": "tc-1"}],
    )
    trailing = HumanMessage(content="after tool")
    trailing.id = "human-after"
    checkpointer.store["repair-live-thread"] = {
        "channel_values": {"messages": [broken_ai, trailing]}
    }

    await _repair_incomplete_tool_calls(
        SimpleNamespace(agent=loop),
        {"configurable": {"thread_id": "repair-live-thread"}},
    )

    state = await loop.aget_state({"configurable": {"thread_id": "repair-live-thread"}})

    assert [msg.__class__.__name__ for msg in state.values["messages"]] == [
        "AIMessage",
        "ToolMessage",
        "HumanMessage",
    ]
    assert [getattr(msg, "content", None) for msg in state.values["messages"]] == [
        "",
        "Error: task was interrupted (server restart or timeout). Results unavailable.",
        "after tool",
    ]


@pytest.mark.asyncio
async def test_get_thread_history_reads_messages_via_query_loop_state_bridge():
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(text="history reply", checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "history-thread"}}

    async for _ in loop.query(
        {"messages": [{"role": "user", "content": "hello"}]},
        config=config,
    ):
        pass

    fake_agent = SimpleNamespace(agent=loop)
    fake_app = SimpleNamespace(state=SimpleNamespace())
    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
    ):
        history = await get_thread_history(
            "history-thread",
            limit=20,
            truncate=300,
            user_id="u",
            app=fake_app,
        )

    assert history["total"] == 2
    assert history["thread_id"] == "history-thread"
    assert [item["role"] for item in history["messages"]] == ["human", "assistant"]
    assert history["messages"][1]["text"] == "history reply"
