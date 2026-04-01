"""Unit tests for core.runtime.loop QueryLoop."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from core.runtime.loop import QueryLoop
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_registry(*entries):
    reg = ToolRegistry()
    for e in entries:
        reg.register(e)
    return reg


def make_loop(model, registry=None, middleware=None, max_turns=10):
    return QueryLoop(
        model=model,
        system_prompt=SystemMessage(content="You are a test assistant."),
        middleware=middleware or [],
        checkpointer=None,
        registry=registry or make_registry(),
        max_turns=max_turns,
    )


def mock_model_no_tools(text="Hello!"):
    """Model that returns a plain AIMessage (no tool calls)."""
    ai_msg = AIMessage(content=text)
    model = MagicMock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(return_value=ai_msg)
    return model


def mock_model_with_tool_call(tool_name="echo", args=None, call_id="tc-1", then_text="Done"):
    """Model that first responds with a tool call, then responds with plain text."""
    args = args or {"message": "hi"}
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{"name": tool_name, "args": args, "id": call_id}],
    )
    final_msg = AIMessage(content=then_text)
    model = MagicMock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(side_effect=[tool_call_msg, final_msg])
    return model


# ---------------------------------------------------------------------------
# Tests: no tool calls → single agent chunk
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_tool_calls_yields_one_agent_chunk():
    model = mock_model_no_tools("Hello world")
    loop = make_loop(model)

    chunks = []
    async for chunk in loop.astream({"messages": [{"role": "user", "content": "hi"}]}):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert "agent" in chunks[0]
    msgs = chunks[0]["agent"]["messages"]
    assert len(msgs) == 1
    assert msgs[0].content == "Hello world"


@pytest.mark.asyncio
async def test_no_tool_calls_model_called_once():
    model = mock_model_no_tools()
    loop = make_loop(model)

    async for _ in loop.astream({"messages": [{"role": "user", "content": "hi"}]}):
        pass

    assert model.ainvoke.call_count == 1


# ---------------------------------------------------------------------------
# Tests: with tool calls → agent chunk + tools chunk
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_call_yields_agent_then_tools():
    model = mock_model_with_tool_call()

    # Register a simple echo tool
    def echo_handler(message: str) -> str:
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "echo", "parameters": {"type": "object", "properties": {}}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=True,
    )
    registry = make_registry(entry)
    loop = make_loop(model, registry=registry)

    chunks = []
    async for chunk in loop.astream({"messages": [{"role": "user", "content": "call echo"}]}):
        chunks.append(chunk)

    # First chunk: agent (with tool_calls)
    # Second chunk: tools (ToolMessage results)
    # Third chunk: agent (final text response)
    agent_chunks = [c for c in chunks if "agent" in c]
    tools_chunks = [c for c in chunks if "tools" in c]

    assert len(agent_chunks) >= 1
    assert len(tools_chunks) >= 1

    # Tool result should be a ToolMessage
    tool_msgs = tools_chunks[0]["tools"]["messages"]
    assert len(tool_msgs) == 1
    assert isinstance(tool_msgs[0], ToolMessage)


@pytest.mark.asyncio
async def test_tool_call_result_content():
    model = mock_model_with_tool_call(tool_name="echo", args={"message": "test-val"})

    def echo_handler(message: str) -> str:
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "d", "parameters": {}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=False,
    )
    loop = make_loop(model, registry=make_registry(entry))

    tool_results = []
    async for chunk in loop.astream({"messages": [{"role": "user", "content": "x"}]}):
        if "tools" in chunk:
            tool_results.extend(chunk["tools"]["messages"])

    assert len(tool_results) == 1
    assert "echo: test-val" in tool_results[0].content


# ---------------------------------------------------------------------------
# Tests: max_turns guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_turns_stops_loop():
    """Agent that always calls a tool should stop at max_turns."""

    def noop_handler() -> str:
        return "ok"

    entry = ToolEntry(
        name="noop",
        mode=ToolMode.INLINE,
        schema={"name": "noop", "description": "d", "parameters": {}},
        handler=noop_handler,
        source="test",
        is_concurrency_safe=True,
    )

    # Build a model that always returns a tool call
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{"name": "noop", "args": {}, "id": "tc-1"}],
    )
    model = MagicMock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(return_value=tool_call_msg)

    loop = make_loop(model, registry=make_registry(entry), max_turns=3)

    chunks = []
    async for chunk in loop.astream({"messages": [{"role": "user", "content": "go"}]}):
        chunks.append(chunk)

    # Should stop after 3 turns (3 agent + 3 tool chunks = 6 total)
    assert len(chunks) <= 6
    assert model.ainvoke.call_count == 3


# ---------------------------------------------------------------------------
# Tests: input parsing
# ---------------------------------------------------------------------------

def test_parse_input_dict_messages():
    msgs = QueryLoop._parse_input({"messages": [{"role": "user", "content": "hello"}]})
    assert len(msgs) == 1
    assert isinstance(msgs[0], HumanMessage)
    assert msgs[0].content == "hello"


def test_parse_input_langchain_messages():
    human = HumanMessage(content="hi")
    msgs = QueryLoop._parse_input({"messages": [human]})
    assert msgs[0] is human


def test_parse_input_empty():
    assert QueryLoop._parse_input({}) == []
    assert QueryLoop._parse_input({"messages": []}) == []
