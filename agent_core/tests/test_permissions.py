"""O2 — PermissionPolicy gates tool calls via the can_use_tool seam."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from agent_core import Agent, PermissionPolicy
from agent_core.builtins import default_toolset
from agent_core.tests.fakes import FakeChatModel, ai_tool_call


def _tool_meta(msg: ToolMessage) -> dict:
    return msg.additional_kwargs.get("tool_result_meta", {})


def test_deny_blocks_tool():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            model = FakeChatModel([
                ai_tool_call("write_file", {"path": "x.txt", "content": "nope"}, call_id="w"),
                AIMessage(content="ok"),
            ])
            agent = Agent(
                model=model,
                tools=default_toolset(tmp),
                workspace_root=tmp,
                can_use_tool=PermissionPolicy(deny=["write_*"]),
            )
            result = await agent.ainvoke("write a file")
            tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
            assert tool_msgs and _tool_meta(tool_msgs[0]).get("kind") == "permission_denied"
            assert not (Path(tmp) / "x.txt").exists()  # tool never ran

    asyncio.run(run())


def test_allow_passes_other_tools():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            model = FakeChatModel([
                ai_tool_call("run_bash", {"command": "echo allowed"}, call_id="b"),
                AIMessage(content="done"),
            ])
            # default allow, only write_* denied -> run_bash proceeds
            agent = Agent(
                model=model,
                tools=default_toolset(tmp),
                workspace_root=tmp,
                can_use_tool=PermissionPolicy(deny=["write_*"]),
            )
            result = await agent.ainvoke("echo")
            tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
            assert tool_msgs and _tool_meta(tool_msgs[0]).get("kind") == "success"
            assert "allowed" in tool_msgs[0].content

    asyncio.run(run())


def test_default_deny_with_allowlist():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "data.txt").write_text("hello")
            model = FakeChatModel([
                ai_tool_call("read_file", {"path": "data.txt"}, call_id="r"),
                ai_tool_call("run_bash", {"command": "echo hi"}, call_id="b"),
                AIMessage(content="done"),
            ])
            agent = Agent(
                model=model,
                tools=default_toolset(tmp),
                workspace_root=tmp,
                can_use_tool=PermissionPolicy(default="deny", allow=["read_file"]),
            )
            result = await agent.ainvoke("read then bash")
            by_name = {m.name: m for m in result["messages"] if isinstance(m, ToolMessage)}
            assert _tool_meta(by_name["read_file"]).get("kind") == "success"
            assert "hello" in by_name["read_file"].content
            assert _tool_meta(by_name["run_bash"]).get("kind") == "permission_denied"

    asyncio.run(run())


def test_policy_decide_precedence():
    p = PermissionPolicy(default="allow", deny=["danger_*"], allow=["danger_safe"], ask=["maybe_*"])
    assert p.decide("danger_rm") == "deny"
    assert p.decide("danger_safe") == "deny"  # deny matched first (danger_*)
    assert p.decide("maybe_x") == "ask"
    assert p.decide("anything") == "allow"
    bd = PermissionPolicy(default="allow", block_destructive=True)
    assert bd.decide("x", is_destructive=True) == "ask"
    assert bd.decide("x", is_destructive=False) == "allow"
