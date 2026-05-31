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


class FlakyChatModel:
    """Raises on the first ``fail_times`` calls, then replays a script. Used to
    exercise retry middleware."""

    def __init__(self, fail_times: int, script: list[Any], exc: type[BaseException] = RuntimeError) -> None:
        self._fail_times = fail_times
        self._script = list(script)
        self._exc = exc
        self._calls = 0
        self._i = 0
        self.model_name = "flaky"

    def bind_tools(self, tools: list) -> "FlakyChatModel":
        return self

    async def ainvoke(self, messages: list) -> AIMessage:
        self._calls += 1
        if self._calls <= self._fail_times:
            raise self._exc(f"transient failure #{self._calls}")
        item = self._script[self._i]
        self._i += 1
        return item() if callable(item) else item


class RoutingFakeModel:
    """A shared model that dispatches to per-route scripts by substring match on
    the concatenated message *content*. Models the real design where parent and
    child share one (stateless) model client.

    ``routes`` is a list of ``(substring, [AIMessage, ...])``; the first route
    whose substring appears in the call's message content is used, advancing that
    route's own cursor.
    """

    def __init__(self, routes: list[tuple[str, list[Any]]], model_name: str = "router") -> None:
        self._routes = [[sub, list(msgs), 0] for sub, msgs in routes]
        self.model_name = model_name
        self.calls: list[list] = []

    def bind_tools(self, tools: list) -> "RoutingFakeModel":
        return self

    async def ainvoke(self, messages: list) -> AIMessage:
        self.calls.append(list(messages))
        text = " ".join(str(getattr(m, "content", "")) for m in messages)
        for route in self._routes:
            sub, msgs, cursor = route
            if sub in text and cursor < len(msgs):
                route[2] = cursor + 1
                item = msgs[cursor]
                return item() if callable(item) else item
        return AIMessage(content="(no route matched)")
