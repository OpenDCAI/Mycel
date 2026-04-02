"""Local runtime middleware protocol and request/response types.

This replaces the phantom `langchain.agents.middleware.types` dependency for
the current runtime stack.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any

from langchain_core.messages import ToolMessage


@dataclass(frozen=True)
class ModelRequest:
    model: Any
    messages: list
    system_message: Any = None
    tools: list | None = None

    def override(self, **changes: Any) -> "ModelRequest":
        return replace(self, **changes)


@dataclass(frozen=True)
class ModelResponse:
    result: list
    request_messages: list | None = None
    prepared_request: "ModelRequest" | None = None


ModelCallResult = ModelResponse


@dataclass(frozen=True)
class ToolCallRequest:
    tool_call: dict
    tool: Any = None
    state: Any = None
    runtime: Any = None

    def override(self, **changes: Any) -> "ToolCallRequest":
        return replace(self, **changes)


class AgentMiddleware:
    """Minimal chain-of-responsibility middleware base for the runtime stack."""

    tools: list[Any] = []

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(request)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage],
    ) -> ToolMessage:
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> ToolMessage:
        return await handler(request)
