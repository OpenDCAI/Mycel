"""O3 — abort wiring + multi-agent lifecycle (stop / timeout / cascade)."""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, ToolMessage

from agent_core import Agent, TerminalReason
from agent_core.abort import AbortController
from agent_core.multiagent import MultiAgentRuntime
from agent_core.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema
from agent_core.tests.fakes import FakeChatModel, HangingChatModel, ai_tool_call


def test_abort_before_run_makes_no_model_call():
    async def run():
        model = FakeChatModel([AIMessage(content="should not be called")])
        agent = Agent(model=model, registry=ToolRegistry())
        agent.abort()
        result = await agent.ainvoke("hi")
        assert result["reason"] == TerminalReason.aborted.value
        assert model.calls == []  # loop bailed before the first model call

    asyncio.run(run())


def test_abort_mid_run_via_tool():
    async def run():
        ctrl = AbortController()

        def halt() -> str:
            ctrl.abort()
            return "halting"

        reg = ToolRegistry()
        reg.register(ToolEntry(
            name="halt", mode=ToolMode.INLINE,
            schema=make_tool_schema(name="halt", description="halt", properties={}),
            handler=halt, source="test",
        ))
        model = FakeChatModel([
            ai_tool_call("halt", {}, call_id="h1"),
            ai_tool_call("halt", {}, call_id="h2"),  # must NOT be reached
            AIMessage(content="done"),
        ])
        agent = Agent(model=model, registry=reg, abort_controller=ctrl)
        result = await agent.ainvoke("go")
        assert result["reason"] == TerminalReason.aborted.value
        assert len(model.calls) == 1  # only turn 1 hit the model
        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert tool_msgs and tool_msgs[0].content == "halting"

    asyncio.run(run())


def test_stop_all_cascades_to_children():
    async def run():
        runtime = MultiAgentRuntime(model=FakeChatModel([]))
        child_a = runtime.build_agent(name="a")
        child_b = runtime.build_agent(name="b")
        assert not child_a.abort_controller.is_aborted()
        runtime.stop_all()
        assert child_a.abort_controller.is_aborted()
        assert child_b.abort_controller.is_aborted()

    asyncio.run(run())


def test_spawn_timeout_marks_entry():
    async def run():
        runtime = MultiAgentRuntime(model=HangingChatModel(delay=5.0))
        try:
            await runtime.spawn(name="slow", prompt="do slow thing", timeout=0.1)
            raised = False
        except TimeoutError:
            raised = True
        assert raised
        entry = runtime.registry.by_name("slow")
        assert entry is not None and entry.status == "timeout"
        assert entry.abort_controller is not None and entry.abort_controller.is_aborted()

    asyncio.run(run())


def test_background_stop():
    async def run():
        runtime = MultiAgentRuntime(model=HangingChatModel(delay=5.0))
        info = await runtime.spawn(name="bg", prompt="hang", background=True)
        task_id = info["task_id"]
        await asyncio.sleep(0)  # let the task start
        stopped = runtime.stop(task_id)
        assert stopped["status"] == "stopped"
        # drain the cancelled task so it doesn't warn
        task = runtime._tasks[task_id]
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        assert runtime.registry.by_id(task_id).abort_controller.is_aborted()

    asyncio.run(run())
