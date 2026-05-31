"""O1 — concurrency-safe tool calls run in parallel; ordering is preserved."""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, ToolMessage

from agent_core import Agent
from agent_core.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema
from agent_core.tests.fakes import FakeChatModel


def _schema(name: str) -> dict:
    return make_tool_schema(name=name, description=name, properties={})


def _multi_tool_call(*names: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": n, "args": {}, "id": f"c{i}", "type": "tool_call"} for i, n in enumerate(names)],
    )


def test_concurrent_safe_tools_run_in_parallel():
    """Two concurrency-safe tools each await a 2-party barrier. They can only both
    pass if dispatched concurrently; serial dispatch would deadlock and time out."""

    async def run():
        barrier = asyncio.Barrier(2)

        async def probe_a() -> str:
            await asyncio.wait_for(barrier.wait(), timeout=2.0)
            return "A passed"

        async def probe_b() -> str:
            await asyncio.wait_for(barrier.wait(), timeout=2.0)
            return "B passed"

        reg = ToolRegistry()
        for name, handler in (("probe_a", probe_a), ("probe_b", probe_b)):
            reg.register(ToolEntry(
                name=name, mode=ToolMode.INLINE, schema=_schema(name),
                handler=handler, source="test", is_concurrency_safe=True, is_read_only=True,
            ))
        model = FakeChatModel([_multi_tool_call("probe_a", "probe_b"), AIMessage(content="both done")])
        agent = Agent(model=model, registry=reg)
        result = await agent.ainvoke("go")
        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        contents = {m.content for m in tool_msgs}
        assert "A passed" in contents and "B passed" in contents

    asyncio.run(run())


def test_unsafe_tool_creates_ordering_boundary():
    """[safe, unsafe, safe] -> safe#1 flushes before unsafe runs; safe#2 after.
    Result order matches call order regardless of concurrency."""

    async def run():
        order: list[str] = []

        def make(name: str, safe: bool):
            def handler() -> str:
                order.append(name)
                return name
            return ToolEntry(
                name=name, mode=ToolMode.INLINE, schema=_schema(name),
                handler=handler, source="test", is_concurrency_safe=safe, is_read_only=safe,
            )

        reg = ToolRegistry()
        reg.register(make("s1", True))
        reg.register(make("u", False))
        reg.register(make("s2", True))
        model = FakeChatModel([_multi_tool_call("s1", "u", "s2"), AIMessage(content="done")])
        agent = Agent(model=model, registry=reg)
        result = await agent.ainvoke("go")
        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        # results in call order
        assert [m.content for m in tool_msgs] == ["s1", "u", "s2"]
        # execution honored the unsafe boundary: s1 before u, u before s2
        assert order.index("s1") < order.index("u") < order.index("s2")

    asyncio.run(run())
