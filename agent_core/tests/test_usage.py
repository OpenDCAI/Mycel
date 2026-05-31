"""O4 — usage accounting, budget caps, and prompt-caching annotation."""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, SystemMessage

from agent_core import (
    Agent,
    PromptCachingMiddleware,
    TerminalReason,
    UsageMeter,
    token_pricer,
)
from agent_core.middleware import ModelRequest
from agent_core.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema
from agent_core.tests.fakes import FakeChatModel


def _ai(content="", *, tool=None, in_t=0, out_t=0, cid="c"):
    kwargs = {"content": content, "usage_metadata": {"input_tokens": in_t, "output_tokens": out_t, "total_tokens": in_t + out_t}}
    if tool:
        kwargs["tool_calls"] = [{"name": tool, "args": {}, "id": cid, "type": "tool_call"}]
    return AIMessage(**kwargs)


def _noop_tool():
    return ToolEntry(
        name="noop", mode=ToolMode.INLINE,
        schema=make_tool_schema(name="noop", description="noop", properties={}),
        handler=lambda: "ok", source="test", is_concurrency_safe=True, is_read_only=True,
    )


def test_usage_accumulates():
    async def run():
        model = FakeChatModel([_ai("done", in_t=100, out_t=40)])
        agent = Agent(model=model, registry=ToolRegistry())
        await agent.ainvoke("hi")
        assert agent.usage.input_tokens == 100
        assert agent.usage.output_tokens == 40
        assert agent.usage.total_tokens == 140
        assert agent.usage.turns == 1

    asyncio.run(run())


def test_budget_usd_terminates():
    async def run():
        reg = ToolRegistry()
        reg.register(_noop_tool())
        # each turn: 1000 in + 1000 out tokens; pricer $1/1k each -> $2.00/turn
        model = FakeChatModel([lambda: _ai(tool="noop", in_t=1000, out_t=1000) for _ in range(10)])
        agent = Agent(
            model=model, registry=reg, max_turns=20,
            usage_meter=UsageMeter(token_pricer(1.0, 1.0)), max_budget_usd=3.0,
        )
        result = await agent.ainvoke("spend")
        assert result["reason"] == TerminalReason.budget_exceeded.value
        assert agent.usage.cost_usd >= 3.0

    asyncio.run(run())


def test_max_total_tokens_terminates():
    async def run():
        reg = ToolRegistry()
        reg.register(_noop_tool())
        model = FakeChatModel([lambda: _ai(tool="noop", in_t=500, out_t=500) for _ in range(10)])
        agent = Agent(model=model, registry=reg, max_turns=20, max_total_tokens=2500)
        result = await agent.ainvoke("spend tokens")
        assert result["reason"] == TerminalReason.budget_exceeded.value
        assert agent.usage.total_tokens >= 2500

    asyncio.run(run())


def test_prompt_caching_annotates_request():
    mw = PromptCachingMiddleware()
    req = ModelRequest(
        model=object(),
        messages=[],
        system_message=SystemMessage(content="you are helpful"),
        tools=[{"name": "a"}, {"name": "b"}],
    )
    out = mw._apply(req)
    blocks = out.system_message.content
    assert isinstance(blocks, list) and blocks[-1]["cache_control"] == {"type": "ephemeral"}
    assert blocks[-1]["text"] == "you are helpful"
    assert out.tools[-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in out.tools[0]  # only the last tool is the breakpoint


def test_prompt_caching_in_loop():
    async def run():
        model = FakeChatModel([AIMessage(content="hi")])
        agent = Agent(
            model=model, registry=ToolRegistry(),
            system_prompt="be terse", middleware=[PromptCachingMiddleware()],
        )
        await agent.ainvoke("go")
        # the model received a system message with a cache_control block
        first_call = model.calls[0]
        sys = next(m for m in first_call if isinstance(m, SystemMessage))
        assert isinstance(sys.content, list) and sys.content[-1]["cache_control"] == {"type": "ephemeral"}

    asyncio.run(run())
