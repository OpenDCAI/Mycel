"""Phase 4 — optional RetryMiddleware recovers transient model failures."""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage

from agent_core import Agent, TerminalReason
from agent_core.recovery import RetryMiddleware
from agent_core.registry import ToolRegistry
from agent_core.tests.fakes import FlakyChatModel


def test_retry_recovers_transient_failure():
    async def run():
        model = FlakyChatModel(fail_times=2, script=[AIMessage(content="recovered answer")])
        agent = Agent(
            model=model,
            registry=ToolRegistry(),
            middleware=[RetryMiddleware(max_retries=2)],
        )
        result = await agent.ainvoke("please answer")
        assert result["reason"] == TerminalReason.completed.value
        assert "recovered answer" in result["messages"][-1].content

    asyncio.run(run())


def test_retry_exhausted_surfaces_model_error():
    async def run():
        model = FlakyChatModel(fail_times=5, script=[AIMessage(content="never reached")])
        agent = Agent(
            model=model,
            registry=ToolRegistry(),
            middleware=[RetryMiddleware(max_retries=1)],
        )
        result = await agent.ainvoke("please answer")
        # retries exhausted -> loop records a terminal model_error (no raise)
        assert result["reason"] == TerminalReason.model_error.value

    asyncio.run(run())
