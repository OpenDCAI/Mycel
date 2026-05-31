"""Phase 3 — lightweight multi-agent: handoff delivery + spawn."""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, ToolMessage

from agent_core import Agent, TerminalReason
from agent_core.multiagent import MessageBus, MultiAgentRuntime, SteeringMiddleware
from agent_core.multiagent.bus import BusMessage
from agent_core.registry import ToolRegistry
from agent_core.tests.fakes import FakeChatModel, RoutingFakeModel, ai_tool_call


def test_steering_injects_handoff_message():
    """A message enqueued for an agent is delivered (injected) before its turn."""

    async def run():
        bus = MessageBus()
        bus.enqueue("B", BusMessage(sender="A", content="please summarize the doc"))
        model = FakeChatModel([AIMessage(content="ok, summarizing")])
        agent = Agent(model=model, registry=ToolRegistry(), middleware=[SteeringMiddleware(agent_name="B", bus=bus)])
        result = await agent.ainvoke("start", thread_id="B")
        # the model's first call must have seen the injected handoff message
        seen = " ".join(str(getattr(m, "content", "")) for m in model.calls[0])
        assert "message from A" in seen and "summarize the doc" in seen
        assert result["reason"] == TerminalReason.completed.value

    asyncio.run(run())


def test_spawn_returns_child_result():
    """Parent spawns a child via the spawn_agent tool; child runs on the shared
    model and its result flows back into the parent's answer."""

    async def run():
        model = RoutingFakeModel([
            # child: anything containing CHILD-TASK
            ("CHILD-TASK", [AIMessage(content="child result: 42 widgets")]),
            # parent: anything containing PARENT-JOB
            ("PARENT-JOB", [
                ai_tool_call(
                    "spawn_agent",
                    {"name": "researcher", "prompt": "CHILD-TASK: count the widgets"},
                    call_id="s1",
                ),
                AIMessage(content="final: the child said 42 widgets"),
            ]),
        ])
        runtime = MultiAgentRuntime(model=model)
        parent = runtime.build_agent(name="orchestrator")
        result = await parent.ainvoke("PARENT-JOB: delegate the widget count", thread_id="orchestrator")

        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert tool_msgs and "child result: 42 widgets" in tool_msgs[0].content
        assert result["reason"] == TerminalReason.completed.value
        assert "42 widgets" in result["messages"][-1].content
        # child was registered
        assert runtime.registry.by_name("researcher") is not None
        assert runtime.registry.by_name("researcher").status == "done"

    asyncio.run(run())


def test_background_spawn_and_task_output():
    """Background spawn returns a task id; task_output blocks for the result."""

    async def run():
        model = RoutingFakeModel([
            ("CHILD-BG", [AIMessage(content="bg child done: report ready")]),
            ("PARENT-BG", [
                ai_tool_call(
                    "spawn_agent",
                    {"name": "worker", "prompt": "CHILD-BG: build the report", "background": True},
                    call_id="s1",
                ),
                # after spawning in background, fetch its output
                lambda: ai_tool_call("task_output", {"task_id": "task_1"}, call_id="o1"),
                AIMessage(content="parent: got report ready"),
            ]),
        ])
        runtime = MultiAgentRuntime(model=model)
        parent = runtime.build_agent(name="boss")
        result = await parent.ainvoke("PARENT-BG: kick off the report", thread_id="boss")

        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        # first tool result = spawn confirmation, second = task_output text
        assert any("running" in m.content for m in tool_msgs)
        assert any("report ready" in m.content for m in tool_msgs)
        assert "report ready" in result["messages"][-1].content

    asyncio.run(run())


def test_send_message_between_agents():
    """One agent's send_message reaches another agent's bus queue."""

    async def run():
        runtime = MultiAgentRuntime(model=FakeChatModel([]))
        # simulate agent 'A' sending to 'B'
        info = runtime.send_message(to="B", content="ping", sender="A")
        assert info["delivered_to"] == "B" and info["pending"] == 1
        drained = runtime.bus.drain("B")
        assert len(drained) == 1 and drained[0].sender == "A" and drained[0].content == "ping"

    asyncio.run(run())
