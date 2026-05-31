"""Phase 1 — the minimal loop runs end-to-end against a scripted model."""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, ToolMessage

from agent_core.adapters import InMemoryCheckpointStore
from agent_core.loop import QueryLoop, TerminalReason
from agent_core.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema
from agent_core.runner import ToolRunner
from agent_core.tests.fakes import FakeChatModel, ai_tool_call


def _add_tool() -> ToolEntry:
    return ToolEntry(
        name="add",
        mode=ToolMode.INLINE,
        schema=make_tool_schema(
            name="add",
            description="Add two integers and return the sum.",
            properties={"a": {"type": "integer"}, "b": {"type": "integer"}},
            required=["a", "b"],
        ),
        handler=lambda a, b: str(a + b),
        source="local",
        is_read_only=True,
        is_concurrency_safe=True,
    )


def test_completes_without_tools():
    async def run():
        model = FakeChatModel([AIMessage(content="hello there")])
        loop = QueryLoop(model=model, registry=ToolRegistry())
        result = await loop.ainvoke("hi")
        assert result["reason"] == TerminalReason.completed.value
        assert any(isinstance(m, AIMessage) and "hello" in m.content for m in result["messages"])

    asyncio.run(run())


def test_tool_then_answer_innermost_handler():
    async def run():
        reg = ToolRegistry()
        reg.register(_add_tool())
        model = FakeChatModel([
            ai_tool_call("add", {"a": 2, "b": 3}),
            AIMessage(content="The sum is 5."),
        ])
        loop = QueryLoop(model=model, registry=reg)  # no ToolRunner -> innermost handler
        result = await loop.ainvoke("add 2 and 3")
        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert tool_msgs and tool_msgs[0].content == "5"
        assert result["reason"] == TerminalReason.completed.value
        assert any(isinstance(m, AIMessage) and "sum is 5" in m.content for m in result["messages"])

    asyncio.run(run())


def test_tool_via_toolrunner_middleware():
    async def run():
        reg = ToolRegistry()
        reg.register(_add_tool())
        model = FakeChatModel([
            ai_tool_call("add", {"a": 10, "b": 7}),
            AIMessage(content="done: 17"),
        ])
        loop = QueryLoop(model=model, registry=reg, middleware=[ToolRunner(reg)])
        result = await loop.ainvoke("add")
        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert tool_msgs and tool_msgs[0].content == "17"
        # ToolRunner materializes structured metadata
        meta = tool_msgs[0].additional_kwargs.get("tool_result_meta", {})
        assert meta.get("kind") == "success"
        assert result["reason"] == TerminalReason.completed.value

    asyncio.run(run())


def test_validation_error_via_toolrunner():
    async def run():
        reg = ToolRegistry()
        reg.register(_add_tool())
        # missing required "b"
        model = FakeChatModel([
            ai_tool_call("add", {"a": 1}),
            AIMessage(content="acknowledged"),
        ])
        loop = QueryLoop(model=model, registry=reg, middleware=[ToolRunner(reg)])
        result = await loop.ainvoke("bad call")
        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert tool_msgs
        meta = tool_msgs[0].additional_kwargs.get("tool_result_meta", {})
        assert meta.get("kind") == "error"
        assert "InputValidationError" in tool_msgs[0].content

    asyncio.run(run())


def test_checkpoint_round_trip():
    async def run():
        store = InMemoryCheckpointStore()
        reg = ToolRegistry()
        # first session: one assistant turn
        m1 = FakeChatModel([AIMessage(content="first answer")])
        loop1 = QueryLoop(model=m1, registry=reg, checkpoint_store=store)
        await loop1.ainvoke("first question", config={"configurable": {"thread_id": "t1"}})
        saved = await store.load("t1")
        assert saved is not None and len(saved.messages) >= 2  # human + ai

        # second session: same thread should hydrate prior history before the new turn
        m2 = FakeChatModel([AIMessage(content="second answer")])
        loop2 = QueryLoop(model=m2, registry=reg, checkpoint_store=store)
        await loop2.ainvoke("second question", config={"configurable": {"thread_id": "t1"}})
        # the model on the 2nd run must have seen the hydrated history
        first_call = m2.calls[0]
        contents = " ".join(str(getattr(m, "content", "")) for m in first_call)
        assert "first question" in contents and "first answer" in contents
        assert "second question" in contents

    asyncio.run(run())


def test_max_turns():
    async def run():
        reg = ToolRegistry()
        reg.register(_add_tool())
        # always asks for a tool call -> never terminates on its own
        model = FakeChatModel([lambda: ai_tool_call("add", {"a": 1, "b": 1}, call_id="c") for _ in range(10)])
        loop = QueryLoop(model=model, registry=reg, max_turns=3)
        result = await loop.ainvoke("loop forever")
        assert result["reason"] == TerminalReason.max_turns.value

    asyncio.run(run())
