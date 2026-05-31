"""Builtin multi-agent tools: spawn_agent, send_message, task_output.

Each is wired to a ``MultiAgentRuntime`` and the calling agent's name (so
``send_message`` records the right sender).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_core.registry import ToolEntry, ToolMode, make_tool_schema

if TYPE_CHECKING:
    from agent_core.multiagent.runtime import MultiAgentRuntime


def multiagent_tools(runtime: "MultiAgentRuntime", *, agent_name: str) -> list[ToolEntry]:
    async def spawn_agent(name: str, prompt: str, subagent_type: str = "general", background: bool = False) -> str:
        result = await runtime.spawn(name=name, prompt=prompt, subagent_type=subagent_type, background=background)
        if background:
            return f"spawned '{name}' as {result['task_id']} (running)"
        return result.get("text") or f"agent '{name}' finished with status {result['status']}"

    def send_message(to: str, content: str) -> str:
        info = runtime.send_message(to=to, content=content, sender=agent_name)
        return f"delivered to '{to}' (pending {info['pending']})"

    async def task_output(task_id: str, block: bool = True) -> str:
        info = await runtime.task_output(task_id=task_id, block=block)
        if "error" in info:
            return f"<error>{info['error']}</error>"
        return info.get("text") or f"{task_id}: {info.get('status')}"

    return [
        ToolEntry(
            name="spawn_agent",
            mode=ToolMode.INLINE,
            schema=make_tool_schema(
                name="spawn_agent",
                description="Spawn a sub-agent to handle a task. Returns its result (or a task id if background).",
                properties={
                    "name": {"type": "string", "description": "unique name for the sub-agent"},
                    "prompt": {"type": "string", "description": "the task for the sub-agent"},
                    "subagent_type": {"type": "string"},
                    "background": {"type": "boolean"},
                },
                required=["name", "prompt"],
            ),
            handler=spawn_agent,
            source="builtin",
            search_hint="spawn delegate sub-agent",
        ),
        ToolEntry(
            name="send_message",
            mode=ToolMode.INLINE,
            schema=make_tool_schema(
                name="send_message",
                description="Send a message to another running agent by name; delivered before its next turn.",
                properties={"to": {"type": "string"}, "content": {"type": "string"}},
                required=["to", "content"],
            ),
            handler=send_message,
            source="builtin",
            search_hint="send message handoff agent",
            is_concurrency_safe=True,
        ),
        ToolEntry(
            name="task_output",
            mode=ToolMode.INLINE,
            schema=make_tool_schema(
                name="task_output",
                description="Get the result of a backgrounded sub-agent task (blocks until done unless block=false).",
                properties={"task_id": {"type": "string"}, "block": {"type": "boolean"}},
                required=["task_id"],
            ),
            handler=task_output,
            source="builtin",
            search_hint="poll await background task result",
            is_read_only=True,
        ),
    ]
