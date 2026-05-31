"""Test doubles for driving the loop without a real LLM."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage


class FakeChatModel:
    """A scripted chat model. Each ``ainvoke`` returns the next scripted message.

    Implements only what ``QueryLoop`` calls: ``bind_tools`` and ``ainvoke``.
    """

    def __init__(self, script: list[Any], model_name: str = "fake") -> None:
        self._script = list(script)
        self._i = 0
        self.model_name = model_name
        self.bound_tools: list | None = None
        self.calls: list[list] = []

    def bind_tools(self, tools: list) -> "FakeChatModel":
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages: list) -> AIMessage:
        self.calls.append(list(messages))
        if self._i >= len(self._script):
            return AIMessage(content="(no more scripted responses)")
        item = self._script[self._i]
        self._i += 1
        return item() if callable(item) else item


def ai_tool_call(name: str, args: dict, *, call_id: str = "call_1", content: str = "") -> AIMessage:
    return AIMessage(
        content=content,
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )
