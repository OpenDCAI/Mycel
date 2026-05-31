"""Phase 2 — the Agent facade does real work via builtin tools."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from agent_core import Agent, TerminalReason
from agent_core.adapters import InMemoryCheckpointStore
from agent_core.builtins import default_toolset
from agent_core.tests.fakes import FakeChatModel, ai_tool_call


def test_agent_writes_then_reads_file():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            model = FakeChatModel([
                ai_tool_call("write_file", {"path": "note.txt", "content": "hello core"}, call_id="w"),
                ai_tool_call("read_file", {"path": "note.txt"}, call_id="r"),
                AIMessage(content="The file says: hello core"),
            ])
            agent = Agent(model=model, tools=default_toolset(tmp), workspace_root=tmp)
            result = await agent.ainvoke("write then read note.txt")

            assert result["reason"] == TerminalReason.completed.value
            assert (Path(tmp) / "note.txt").read_text() == "hello core"
            tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
            assert any("hello core" in m.content for m in tool_msgs)
            assert isinstance(result["messages"][-1], AIMessage)
            assert "hello core" in result["messages"][-1].content

    asyncio.run(run())


def test_agent_run_bash():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            model = FakeChatModel([
                ai_tool_call("run_bash", {"command": "echo hi-from-bash"}, call_id="b"),
                AIMessage(content="bash ran"),
            ])
            agent = Agent(model=model, tools=default_toolset(tmp), workspace_root=tmp)
            result = await agent.ainvoke("run echo")
            tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
            assert tool_msgs and "hi-from-bash" in tool_msgs[0].content
            assert "[exit 0]" in tool_msgs[0].content

    asyncio.run(run())


def test_agent_path_containment():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            model = FakeChatModel([
                ai_tool_call("read_file", {"path": "../../etc/passwd"}, call_id="x"),
                AIMessage(content="handled"),
            ])
            agent = Agent(model=model, tools=default_toolset(tmp), workspace_root=tmp)
            result = await agent.ainvoke("escape attempt")
            tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
            # escape is rejected -> tool error surfaced to the model, loop continues
            assert tool_msgs and tool_msgs[0].additional_kwargs.get("tool_result_meta", {}).get("kind") == "error"
            assert "escapes workspace" in tool_msgs[0].content

    asyncio.run(run())


def test_agent_checkpoint_thread():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            store = InMemoryCheckpointStore()
            m1 = FakeChatModel([AIMessage(content="answer one")])
            a1 = Agent(model=m1, tools=default_toolset(tmp), workspace_root=tmp, checkpoint_store=store)
            await a1.ainvoke("q1", thread_id="conv")

            m2 = FakeChatModel([AIMessage(content="answer two")])
            a2 = Agent(model=m2, tools=default_toolset(tmp), workspace_root=tmp, checkpoint_store=store)
            await a2.ainvoke("q2", thread_id="conv")
            seen = " ".join(str(getattr(m, "content", "")) for m in m2.calls[0])
            assert "q1" in seen and "answer one" in seen and "q2" in seen

    asyncio.run(run())
