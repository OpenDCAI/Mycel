from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import ToolMessage

from .errors import InputValidationError
from .registry import ToolRegistry
from .validator import ToolValidator

logger = logging.getLogger(__name__)


class ToolRunner(AgentMiddleware):
    """Innermost middleware: routes all registered tool calls.

    - wrap_model_call: injects inline tool schemas
    - wrap_tool_call: validates, dispatches, normalizes errors
    """

    def __init__(self, registry: ToolRegistry, validator: ToolValidator | None = None):
        self._registry = registry
        self._validator = validator or ToolValidator()

    def _inject_tools(self, request: ModelRequest) -> ModelRequest:
        inline_schemas = self._registry.get_inline_schemas()
        existing_tools = list(request.tools or [])
        # tools can be BaseTool instances or dicts - handle both
        existing_names: set[str] = set()
        for t in existing_tools:
            if isinstance(t, dict):
                name = t.get("name") or t.get("function", {}).get("name")
            else:
                name = getattr(t, "name", None)
            if name:
                existing_names.add(name)
        new_tools = [s for s in inline_schemas if s.get("name") not in existing_names]
        return request.override(tools=existing_tools + new_tools)

    def _extract_call_info(self, request: ToolCallRequest) -> tuple[str, dict, str]:
        tool_call = request.tool_call
        name = tool_call.get("name")
        args = tool_call.get("args", {})
        call_id = tool_call.get("id", "")

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}

        return name, args, call_id

    def _validate_and_run(self, name: str, args: dict, call_id: str) -> ToolMessage:
        entry = self._registry.get(name)
        if entry is None:
            return None  # not our tool

        schema = entry.get_schema()
        try:
            self._validator.validate(schema, args)
        except InputValidationError as e:
            return ToolMessage(
                content=f"InputValidationError: {name} failed due to the following issue:\n{e}",
                tool_call_id=call_id,
                name=name,
            )

        try:
            result = entry.handler(**args)
            if asyncio.iscoroutine(result):
                result = asyncio.get_event_loop().run_until_complete(result)
            return ToolMessage(content=str(result), tool_call_id=call_id, name=name)
        except Exception as e:
            logger.exception("Tool %s execution failed", name)
            return ToolMessage(
                content=f"<tool_use_error>{e}</tool_use_error>",
                tool_call_id=call_id,
                name=name,
            )

    async def _validate_and_run_async(self, name: str, args: dict, call_id: str) -> ToolMessage | None:
        entry = self._registry.get(name)
        if entry is None:
            return None

        schema = entry.get_schema()
        try:
            self._validator.validate(schema, args)
        except InputValidationError as e:
            return ToolMessage(
                content=f"InputValidationError: {name} failed due to the following issue:\n{e}",
                tool_call_id=call_id,
                name=name,
            )

        try:
            if asyncio.iscoroutinefunction(entry.handler):
                result = await entry.handler(**args)
            else:
                # @@@async-tool-offload - synchronous inline tool handlers must never run
                # on the web event loop. Remote filesystem/shell cold starts can block for
                # seconds, so the async path always hops sync handlers to a worker thread.
                result = await asyncio.to_thread(entry.handler, **args)
            if asyncio.iscoroutine(result):
                result = await result
            return ToolMessage(content=str(result), tool_call_id=call_id, name=name)
        except Exception as e:
            logger.exception("Tool %s execution failed", name)
            return ToolMessage(
                content=f"<tool_use_error>{e}</tool_use_error>",
                tool_call_id=call_id,
                name=name,
            )

    # -- Model call wrappers --

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._inject_tools(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._inject_tools(request))

    # -- Tool call wrappers --

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage],
    ) -> ToolMessage:
        name, args, call_id = self._extract_call_info(request)
        result = self._validate_and_run(name, args, call_id)
        if result is not None:
            return result
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> ToolMessage:
        name, args, call_id = self._extract_call_info(request)
        result = await self._validate_and_run_async(name, args, call_id)
        if result is not None:
            return result
        return await handler(request)
