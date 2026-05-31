"""PromptCachingMiddleware — mark the stable prefix (system prompt + tools) with
Anthropic ``cache_control: ephemeral`` so the provider caches it across turns.

Opt-in middleware; provider-specific (Anthropic prompt caching). It only rewrites
the ``ModelRequest`` — placing the cache breakpoint on the system message and the
last tool definition (the longest stable prefix) — so it is harmless to other
providers that ignore unknown keys, and trivially testable without a live API.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain_core.messages import SystemMessage

from agent_core.middleware import AgentMiddleware, ModelRequest, ModelResponse

_CACHE_CONTROL = {"type": "ephemeral"}


class PromptCachingMiddleware(AgentMiddleware):
    def __init__(self, *, cache_system: bool = True, cache_tools: bool = True) -> None:
        self.cache_system = cache_system
        self.cache_tools = cache_tools

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._apply(request))

    def _apply(self, request: ModelRequest) -> ModelRequest:
        changes: dict = {}
        if self.cache_system and request.system_message is not None:
            changes["system_message"] = self._cache_system_message(request.system_message)
        if self.cache_tools and request.tools:
            changes["tools"] = self._cache_last_tool(request.tools)
        return request.override(**changes) if changes else request

    @staticmethod
    def _cache_system_message(system: SystemMessage) -> SystemMessage:
        content = system.content
        if isinstance(content, str):
            blocks = [{"type": "text", "text": content, "cache_control": dict(_CACHE_CONTROL)}]
        elif isinstance(content, list) and content:
            blocks = list(content)
            last = blocks[-1]
            blocks[-1] = {**last, "cache_control": dict(_CACHE_CONTROL)} if isinstance(last, dict) else last
        else:
            return system
        return SystemMessage(content=blocks)

    @staticmethod
    def _cache_last_tool(tools: list) -> list:
        tools = list(tools)
        if tools and isinstance(tools[-1], dict):
            tools[-1] = {**tools[-1], "cache_control": dict(_CACHE_CONTROL)}
        return tools
