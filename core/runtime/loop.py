"""QueryLoop — self-managing agentic tool loop replacing LangGraph create_agent.

Implements CC Pattern 1: Agentic Tool Loop (queryLoop).

Design:
- AsyncGenerator that alternates LLM sampling and tool execution.
- Exposes the same .astream(input, config, stream_mode) interface as CompiledStateGraph.
- Middleware chain (SpillBuffer/Monitor/PromptCaching/Memory/Steering/ToolRunner) is
  preserved exactly — awrap_model_call and awrap_tool_call pass through in order.
- is_concurrency_safe tools execute in parallel; others execute serially.
- Checkpointer (AsyncSqliteSaver) stores/restores message history across calls.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .registry import ToolRegistry

logger = logging.getLogger(__name__)

_NOOP_HANDLER: Any = None  # placeholder for innermost "handler" in middleware chain


class QueryLoop:
    """Self-managing query loop replacing create_agent.

    The .astream() method is an AsyncGenerator that yields dicts compatible
    with LangGraph's stream_mode="updates":
      {"agent": {"messages": [AIMessage(...)]}}
      {"tools": {"messages": [ToolMessage(...), ...]}}

    The checkpointer attribute is set post-construction (mirrors create_agent pattern).
    """

    def __init__(
        self,
        model: Any,
        system_prompt: SystemMessage,
        middleware: list[AgentMiddleware],
        checkpointer: Any,
        registry: ToolRegistry,
        max_turns: int = 100,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.middleware = middleware
        self.checkpointer = checkpointer
        self._registry = registry
        self.max_turns = max_turns

    # -------------------------------------------------------------------------
    # Public streaming interface (LangGraph-compatible)
    # -------------------------------------------------------------------------

    async def astream(
        self,
        input: dict,
        config: dict | None = None,
        stream_mode: str = "updates",
    ) -> AsyncGenerator[dict, None]:
        """Stream agent execution chunks compatible with LangGraph stream_mode='updates'."""
        config = config or {}
        thread_id = config.get("configurable", {}).get("thread_id", "default")

        # Set thread context so MemoryMiddleware can find thread_id via ContextVar
        from sandbox.thread_context import set_current_thread_id
        set_current_thread_id(thread_id)

        # Load message history from checkpointer
        messages = await self._load_messages(thread_id)

        # Parse and append new input messages
        new_msgs = self._parse_input(input)
        messages.extend(new_msgs)

        turn = 0
        while turn < self.max_turns:
            turn += 1

            # --- Call model through middleware chain ---
            response = await self._invoke_model(messages, config)

            # Extract AI message from response
            ai_messages = [m for m in response.result if isinstance(m, AIMessage)]
            if not ai_messages:
                # No AI message — unexpected; treat as terminal
                break
            ai_msg = ai_messages[0]

            # Yield agent update (stream_mode="updates" format)
            yield {"agent": {"messages": [ai_msg]}}

            # Check for tool calls
            tool_calls = getattr(ai_msg, "tool_calls", None) or []
            if not tool_calls:
                # Also check additional_kwargs for older message formats
                tool_calls = ai_msg.additional_kwargs.get("tool_calls", [])

            if not tool_calls:
                # No tool calls → agent is done
                messages.append(ai_msg)
                break

            # Expose current messages for forkContext sub-agent spawning
            from sandbox.thread_context import set_current_messages
            set_current_messages(messages + [ai_msg])

            # --- Execute tools through middleware chain ---
            tool_results = await self._execute_tools(tool_calls, response)

            # Yield tools update
            yield {"tools": {"messages": tool_results}}

            # Advance message history for next turn
            messages.append(ai_msg)
            messages.extend(tool_results)

        # Persist message history
        await self._save_messages(thread_id, messages)

    # -------------------------------------------------------------------------
    # Model invocation through middleware chain
    # -------------------------------------------------------------------------

    async def _invoke_model(self, messages: list, config: dict) -> ModelResponse:
        """Call model through the full middleware chain (awrap_model_call)."""

        async def innermost_handler(request: ModelRequest) -> ModelResponse:
            """Actual model call — innermost of the chain."""
            tools = request.tools or []
            model = request.model

            # Bind tools to model if any
            if tools:
                try:
                    bound = model.bind_tools(tools)
                except Exception:
                    bound = model
            else:
                bound = model

            # Build message list: system + conversation
            call_messages = []
            if request.system_message:
                call_messages.append(request.system_message)
            call_messages.extend(request.messages)

            result = await bound.ainvoke(call_messages)
            if not isinstance(result, list):
                result = [result]
            return ModelResponse(result=result)

        # Build ModelRequest
        inline_schemas = self._registry.get_inline_schemas()
        request = ModelRequest(
            model=self.model,
            messages=messages,
            system_message=self.system_prompt,
            tools=inline_schemas,
        )

        # Walk middleware chain outside-in: each wraps the next.
        # Only include middleware that actually overrides awrap_model_call OR wrap_model_call
        # (not just inherits the base-class NotImplementedError stub).
        handler = innermost_handler
        for mw in reversed(self.middleware):
            if _mw_overrides_model_call(mw):
                handler = _make_model_wrapper(mw, handler)

        return await handler(request)

    # -------------------------------------------------------------------------
    # Tool execution through middleware chain
    # -------------------------------------------------------------------------

    async def _execute_tools(self, tool_calls: list, model_response: ModelResponse) -> list[ToolMessage]:
        """Execute tool calls respecting concurrency safety, via middleware chain."""

        async def _exec_one(tool_call: dict) -> ToolMessage:
            name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
            call_id = tool_call.get("id", "")
            args = tool_call.get("args", {}) or tool_call.get("function", {}).get("arguments", {})

            # Normalise args: might be JSON string
            if isinstance(args, str):
                import json
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}

            normalized_call = {"name": name, "args": args, "id": call_id}
            tc_request = ToolCallRequest(
                tool_call=normalized_call,
                tool=None,
                state={},
                runtime=None,  # type: ignore[arg-type]
            )

            async def innermost_tool_handler(req: ToolCallRequest) -> ToolMessage:
                # Fallback direct dispatch: ToolRunner middleware handles this in
                # production, but without ToolRunner we dispatch from registry directly.
                tc = req.tool_call
                t_name = tc.get("name", "")
                t_id = tc.get("id", "")
                t_args = tc.get("args", {})
                entry = self._registry.get(t_name)
                if entry is None:
                    return ToolMessage(
                        content=f"<tool_use_error>Tool '{t_name}' not found</tool_use_error>",
                        tool_call_id=t_id,
                        name=t_name,
                    )
                try:
                    import asyncio as _asyncio
                    if _asyncio.iscoroutinefunction(entry.handler):
                        result = await entry.handler(**t_args)
                    else:
                        result = await _asyncio.to_thread(entry.handler, **t_args)
                    return ToolMessage(content=str(result), tool_call_id=t_id, name=t_name)
                except Exception as e:
                    return ToolMessage(
                        content=f"<tool_use_error>{e}</tool_use_error>",
                        tool_call_id=t_id,
                        name=t_name,
                    )

            # Build tool handler chain (outside-in).
            # Only include middleware that actually overrides awrap_tool_call.
            tool_handler = innermost_tool_handler
            for mw in reversed(self.middleware):
                if _mw_overrides_tool_call(mw):
                    tool_handler = _make_tool_wrapper(mw, tool_handler)

            return await tool_handler(tc_request)

        # Partition tool calls by concurrency safety
        safe_calls: list[dict] = []
        unsafe_calls: list[dict] = []
        for tc in tool_calls:
            name = tc.get("name") or tc.get("function", {}).get("name", "")
            entry = self._registry.get(name)
            if entry and entry.is_concurrency_safe:
                safe_calls.append(tc)
            else:
                unsafe_calls.append(tc)

        results: dict[int, ToolMessage] = {}

        # Execute safe (read-only) tools concurrently
        if safe_calls:
            safe_indices = [i for i, tc in enumerate(tool_calls) if tc in safe_calls]
            safe_results = await asyncio.gather(*[_exec_one(tc) for tc in safe_calls], return_exceptions=True)
            for idx, res in zip(safe_indices, safe_results):
                if isinstance(res, Exception):
                    tc = tool_calls[idx]
                    results[idx] = ToolMessage(
                        content=f"<tool_use_error>{res}</tool_use_error>",
                        tool_call_id=tc.get("id", ""),
                        name=tc.get("name", ""),
                    )
                else:
                    results[idx] = res

        # Execute unsafe tools serially
        for i, tc in enumerate(tool_calls):
            if tc in unsafe_calls:
                try:
                    results[i] = await _exec_one(tc)
                except Exception as e:
                    results[i] = ToolMessage(
                        content=f"<tool_use_error>{e}</tool_use_error>",
                        tool_call_id=tc.get("id", ""),
                        name=tc.get("name", ""),
                    )

        # Return results in original order
        return [results[i] for i in range(len(tool_calls))]

    # -------------------------------------------------------------------------
    # Checkpointer persistence
    # -------------------------------------------------------------------------

    async def _load_messages(self, thread_id: str) -> list:
        """Load message history from checkpointer (if available)."""
        if self.checkpointer is None:
            return []
        try:
            cfg = {"configurable": {"thread_id": thread_id}}
            checkpoint = await self.checkpointer.aget(cfg)
            if checkpoint is None:
                return []
            return list(checkpoint.get("channel_values", {}).get("messages", []))
        except Exception:
            logger.debug("QueryLoop: could not load checkpoint for thread %s", thread_id)
            return []

    async def _save_messages(self, thread_id: str, messages: list) -> None:
        """Persist message history to checkpointer."""
        if self.checkpointer is None:
            return
        try:
            from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata

            cfg = {"configurable": {"thread_id": thread_id}}
            existing = await self.checkpointer.aget(cfg)
            checkpoint_id = existing["id"] if existing else "1"

            checkpoint: Checkpoint = {
                "v": 1,
                "id": checkpoint_id,
                "ts": "",
                "channel_values": {"messages": messages},
                "channel_versions": {},
                "versions_seen": {},
                "pending_sends": [],
            }
            metadata: CheckpointMetadata = {
                "source": "loop",
                "step": len(messages),
                "writes": {},
                "parents": {},
            }
            await self.checkpointer.aput(cfg, checkpoint, metadata, {})
        except Exception:
            logger.debug("QueryLoop: could not save checkpoint for thread %s", thread_id, exc_info=True)

    # -------------------------------------------------------------------------
    # Input parsing
    # -------------------------------------------------------------------------

    @staticmethod
    def _parse_input(input: dict) -> list:
        """Convert input dict to list of LangChain message objects."""
        raw_messages = input.get("messages", [])
        result = []
        for msg in raw_messages:
            if hasattr(msg, "content"):
                result.append(msg)
            elif isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    result.append(HumanMessage(content=content))
                elif role == "assistant":
                    result.append(AIMessage(content=content))
                else:
                    result.append(HumanMessage(content=content))
        return result


# -------------------------------------------------------------------------
# Closure helpers (avoid late-binding bugs in loop-built lambdas)
# -------------------------------------------------------------------------

def _make_model_wrapper(mw: AgentMiddleware, next_handler):
    """Build an awrap_model_call wrapper that correctly closes over mw and next_handler."""
    async def wrapper(request: ModelRequest) -> ModelResponse:
        return await mw.awrap_model_call(request, next_handler)
    return wrapper


def _make_tool_wrapper(mw: AgentMiddleware, next_handler):
    """Build an awrap_tool_call wrapper that correctly closes over mw and next_handler."""
    async def wrapper(request: ToolCallRequest) -> ToolMessage:
        return await mw.awrap_tool_call(request, next_handler)
    return wrapper


# -------------------------------------------------------------------------
# Middleware override detection helpers
# -------------------------------------------------------------------------

from langchain.agents.middleware.types import AgentMiddleware as _BaseMiddleware


def _mw_overrides_model_call(mw: AgentMiddleware) -> bool:
    """True if mw actually overrides awrap_model_call (not just inherits the base stub)."""
    # Check if awrap_model_call is overridden in the concrete class
    mw_type = type(mw)
    base_fn = getattr(_BaseMiddleware, "awrap_model_call", None)
    own_fn = mw_type.__dict__.get("awrap_model_call")
    if own_fn is not None:
        return True
    # Fall back: check if wrap_model_call is overridden (sync version is acceptable)
    base_sync = getattr(_BaseMiddleware, "wrap_model_call", None)
    own_sync = mw_type.__dict__.get("wrap_model_call")
    return own_sync is not None


def _mw_overrides_tool_call(mw: AgentMiddleware) -> bool:
    """True if mw actually overrides awrap_tool_call (not just inherits the base stub)."""
    mw_type = type(mw)
    own_fn = mw_type.__dict__.get("awrap_tool_call")
    if own_fn is not None:
        return True
    own_sync = mw_type.__dict__.get("wrap_tool_call")
    return own_sync is not None
