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
import copy
import json
import inspect
import logging
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from types import SimpleNamespace
from typing import Any, AsyncGenerator

from core.runtime.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, RemoveMessage, SystemMessage, ToolMessage

from .abort import AbortController
from .registry import ToolMode, ToolRegistry
from .permissions import ToolPermissionContext, evaluate_permission_rules
from .state import AppState, BootstrapConfig, ToolPermissionState, ToolUseContext
from .validator import _required_sets_match

logger = logging.getLogger(__name__)

_NOOP_HANDLER: Any = None  # placeholder for innermost "handler" in middleware chain
_ESCALATED_MAX_OUTPUT_TOKENS = 64000
_FLOOR_OUTPUT_TOKENS = 3000
_CONTEXT_OVERFLOW_SAFETY_BUFFER = 1000
_TRANSIENT_API_MAX_RETRIES = 3
_TRANSIENT_API_BASE_DELAY_SECONDS = 0.5
_PROMPT_TOO_LONG_NOTICE_TEXT = (
    "Prompt is too long. Automatic recovery exhausted. Clear the thread or start a new one."
)


class TerminalReason(str, Enum):
    completed = "completed"
    aborted_streaming = "aborted_streaming"
    aborted_tools = "aborted_tools"
    model_error = "model_error"
    max_turns = "max_turns"
    prompt_too_long = "prompt_too_long"
    blocking_limit = "blocking_limit"
    image_error = "image_error"
    hook_stopped = "hook_stopped"
    stop_hook_prevented = "stop_hook_prevented"


class ContinueReason(str, Enum):
    next_turn = "next_turn"
    api_retry = "api_retry"
    collapse_drain_retry = "collapse_drain_retry"
    reactive_compact_retry = "reactive_compact_retry"
    max_output_tokens_escalate = "max_output_tokens_escalate"
    max_output_tokens_recovery = "max_output_tokens_recovery"
    stop_hook_blocking = "stop_hook_blocking"
    token_budget_continuation = "token_budget_continuation"


@dataclass(frozen=True)
class TerminalState:
    reason: TerminalReason
    turn_count: int
    error: str | None = None


@dataclass(frozen=True)
class ContinueState:
    reason: ContinueReason


@dataclass
class _TrackedTool:
    order: int
    tool_call: dict[str, Any]
    is_concurrency_safe: bool
    status: str = "queued"
    task: asyncio.Task[ToolMessage] | None = None
    result: ToolMessage | None = None


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
        app_state: AppState | None = None,
        runtime: Any = None,
        bootstrap: BootstrapConfig | None = None,
        refresh_tools: Any = None,
        max_turns: int = 100,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.middleware = middleware
        self.checkpointer = checkpointer
        self._registry = registry
        self._app_state = app_state
        self._runtime = runtime
        self._bootstrap = bootstrap
        self._refresh_tools = refresh_tools
        self._memory_middleware = next(
            (mw for mw in middleware if hasattr(mw, "compact_boundary_index")),
            None,
        )
        # @@@sa-02-session-tool-refs
        # These refs must survive across turns within the same loop/session,
        # while turn-local attachment triggers stay ephemeral per ToolUseContext.
        self._tool_read_file_state: dict[str, Any] = {}
        self._tool_loaded_nested_memory_paths: set[str] = set()
        self._tool_discovered_skill_names: set[str] = set()
        self._tool_discovered_tool_names_by_thread: dict[str, set[str]] = {}
        self._tool_abort_controller = AbortController()
        self.max_turns = max_turns
        self.last_terminal: TerminalState | None = None
        self.last_continue: ContinueState | None = None

    # -------------------------------------------------------------------------
    # Public streaming interface (LangGraph-compatible)
    # -------------------------------------------------------------------------

    async def query(
        self,
        input: dict,
        config: dict | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Raw loop generator with an explicit final terminal event."""
        config = config or {}
        thread_id = config.get("configurable", {}).get("thread_id", "default")

        # Set thread context so MemoryMiddleware can find thread_id via ContextVar
        from sandbox.thread_context import set_current_thread_id
        set_current_thread_id(thread_id)

        # Load message history and thread-scoped runtime state from checkpointer
        persisted = await self._hydrate_thread_state_from_checkpoint(thread_id)
        messages = list(persisted["messages"])
        self._restore_discovered_tool_names_from_messages(thread_id, messages)

        # Parse and append new input messages
        new_msgs = self._parse_input(input)
        messages.extend(new_msgs)
        self._sync_app_state(messages=messages, turn_count=0)

        terminal: TerminalState | None = None
        transition: ContinueState | None = None
        pending_system_notices: list[HumanMessage] = []
        max_output_tokens_recovery_count = 0
        has_attempted_reactive_compact = False
        max_output_tokens_override: int | None = None
        transient_api_retry_count = 0

        turn = 0
        try:
            while turn < self.max_turns:
                turn += 1
                tool_context = self._build_tool_use_context(messages, thread_id=thread_id)

                messages_for_query, injected_messages = await self._build_query_messages(messages, config)
                if injected_messages:
                    # @@@steer-persist - queue/steer messages accepted before the
                    # next model call must become durable conversation state, not
                    # request-only hints, or later replay/history lies about what
                    # the user actually said mid-run.
                    messages.extend(injected_messages)
                    self._sync_app_state(messages=messages, turn_count=turn)
                self._sync_tool_context_messages(tool_context, messages_for_query)

                # --- Call model through middleware chain ---
                streamed_tool_results: list[ToolMessage] = []
                pending_tool_results: list[ToolMessage] = []
                used_streaming_overlap = False
                response: ModelResponse | None = None
                ai_msg: AIMessage | None = None
                tool_calls: list[dict[str, Any]] = []
                try:
                    if self._can_stream_tools():
                        used_streaming_overlap = True
                        async for stream_event in self._stream_model_with_tool_overlap(
                            messages_for_query,
                            config,
                            thread_id=thread_id,
                            tool_context=tool_context,
                            max_output_tokens_override=max_output_tokens_override,
                        ):
                            if stream_event["type"] == "message_chunk":
                                yield {"message_chunk": stream_event["chunk"]}
                                continue
                            if stream_event["type"] == "tools":
                                chunk_messages = stream_event["messages"]
                                streamed_tool_results.extend(chunk_messages)
                                yield {"tools": {"messages": chunk_messages}}
                                continue
                            response = stream_event["response"]
                            ai_msg = stream_event["ai_message"]
                            tool_calls = stream_event["tool_calls"]
                            pending_tool_results = stream_event["remaining_tool_results"]
                    else:
                        response = await self._invoke_model(
                            messages_for_query,
                            config,
                            thread_id=thread_id,
                            max_output_tokens_override=max_output_tokens_override,
                        )
                except Exception as exc:
                    self._collect_memory_system_notices(pending_system_notices)
                    handled = await self._handle_model_error_recovery(
                        exc=exc,
                        thread_id=thread_id,
                        messages=messages,
                        turn=turn,
                        transition=transition,
                        max_output_tokens_recovery_count=max_output_tokens_recovery_count,
                        has_attempted_reactive_compact=has_attempted_reactive_compact,
                        max_output_tokens_override=max_output_tokens_override,
                        transient_api_retry_count=transient_api_retry_count,
                    )
                    if handled is not None:
                        messages = handled["messages"]
                        transition = handled["transition"]
                        max_output_tokens_recovery_count = handled["max_output_tokens_recovery_count"]
                        has_attempted_reactive_compact = handled["has_attempted_reactive_compact"]
                        max_output_tokens_override = handled["max_output_tokens_override"]
                        transient_api_retry_count = handled["transient_api_retry_count"]
                        if handled["terminal"] is not None:
                            terminal = handled["terminal"]
                            break
                        self._sync_app_state(messages=messages, turn_count=turn)
                        continue
                    terminal = TerminalState(
                        reason=TerminalReason.model_error,
                        turn_count=turn,
                        error=str(exc),
                    )
                    break

                if response is None or ai_msg is None:
                    ai_messages = [m for m in (response.result if response else []) if isinstance(m, AIMessage)]
                    if not ai_messages:
                        # No AI message — unexpected; treat as terminal
                        terminal = TerminalState(
                            reason=TerminalReason.model_error,
                            turn_count=turn,
                            error="model returned no AIMessage",
                        )
                        break
                    ai_msg = ai_messages[0]
                self._collect_memory_system_notices(pending_system_notices)
                self._sync_tool_context_messages(
                    tool_context,
                    response.request_messages or messages_for_query,
                )

                truncated = self._handle_truncated_response_recovery(
                    ai_msg=ai_msg,
                    messages=messages,
                    turn=turn,
                    max_output_tokens_recovery_count=max_output_tokens_recovery_count,
                    max_output_tokens_override=max_output_tokens_override,
                )
                if truncated is not None:
                    messages = truncated["messages"]
                    transition = truncated["transition"]
                    max_output_tokens_recovery_count = truncated["max_output_tokens_recovery_count"]
                    max_output_tokens_override = truncated["max_output_tokens_override"]
                    self._sync_app_state(messages=messages, turn_count=turn)
                    if truncated["yield_ai"]:
                        yield {"agent": {"messages": [ai_msg]}}
                    if truncated["terminal"] is not None:
                        terminal = truncated["terminal"]
                        break
                    continue

                self._sync_app_state(messages=messages, turn_count=turn)

                if not tool_calls:
                    tool_calls = getattr(ai_msg, "tool_calls", None) or []
                if not tool_calls:
                    # Also check additional_kwargs for older message formats
                    tool_calls = ai_msg.additional_kwargs.get("tool_calls", [])

                if not tool_calls and not self._ai_message_has_visible_content(ai_msg):
                    terminal_followthrough_notice = self._get_terminal_followthrough_notice(messages)
                    if terminal_followthrough_notice is not None:
                        ai_msg = self._build_terminal_followthrough_fallback(terminal_followthrough_notice)

                # Yield agent update (stream_mode="updates" format)
                yield {"agent": {"messages": [ai_msg]}}

                if not tool_calls:
                    # No tool calls → agent is done
                    if self._ai_message_has_visible_content(ai_msg):
                        messages.append(ai_msg)
                    terminal = TerminalState(
                        reason=TerminalReason.completed,
                        turn_count=turn,
                    )
                    break

                # Expose current messages for forkContext sub-agent spawning
                from sandbox.thread_context import set_current_messages
                set_current_messages(messages + [ai_msg])

                if used_streaming_overlap:
                    if pending_tool_results:
                        yield {"tools": {"messages": pending_tool_results}}
                    tool_results = streamed_tool_results + pending_tool_results
                else:
                    # --- Execute tools through middleware chain ---
                    try:
                        tool_results = await self._execute_tools(tool_calls, response, tool_context)
                    except Exception as exc:
                        terminal = TerminalState(
                            reason=TerminalReason.aborted_tools,
                            turn_count=turn,
                            error=str(exc),
                        )
                        break

                    # Yield tools update
                    yield {"tools": {"messages": tool_results}}

                # Advance message history for next turn
                messages.append(ai_msg)
                messages.extend(tool_results)
                await self._refresh_tools_between_turns(tool_context)
                transition = ContinueState(reason=ContinueReason.next_turn)
                max_output_tokens_recovery_count = 0
                has_attempted_reactive_compact = False
                max_output_tokens_override = None
                transient_api_retry_count = 0
                self._sync_app_state(messages=messages, turn_count=turn)
        except asyncio.CancelledError:
            # @@@cancel-persists-live-state - accepted user input from the
            # current run must not evaporate just because the run is cancelled
            # before the next terminal save.
            messages = self._append_system_notices(messages, pending_system_notices)
            await self._save_messages(thread_id, messages)
            self._sync_app_state(messages=messages, turn_count=turn)
            raise

        if terminal is None:
            terminal = TerminalState(
                reason=TerminalReason.max_turns,
                turn_count=turn,
            )

        # Persist message history
        self._collect_memory_system_notices(pending_system_notices)
        terminal_notice = self._build_terminal_notice(terminal)
        if terminal_notice is not None:
            pending_system_notices.append(terminal_notice)
        messages = self._append_system_notices(messages, pending_system_notices)
        await self._save_messages(thread_id, messages)
        self._sync_app_state(messages=messages, turn_count=turn)
        self.last_terminal = terminal
        self.last_continue = transition
        yield {"terminal": terminal, "transition": transition}

    async def astream(
        self,
        input: dict,
        config: dict | None = None,
        stream_mode: str | list[str] = "updates",
    ) -> AsyncGenerator[Any, None]:
        """Stream agent execution chunks compatible with LangGraph stream modes."""
        requested_modes = [stream_mode] if isinstance(stream_mode, str) else list(stream_mode)
        emitted_live_agent_chunks = False
        async for event in self.query(input, config=config):
            if "terminal" in event:
                terminal = event["terminal"]
                if terminal is not None and terminal.reason is not TerminalReason.completed:
                    # @@@astream-terminal-loud-fail
                    # query() always emits a terminal event, but caller-facing
                    # astream() must not turn runtime failures into a silent empty
                    # iterator. Propagate non-completed terminals back to the caller.
                    raise RuntimeError(self._terminal_error_text(terminal))
                continue
            if isinstance(stream_mode, str):
                if "message_chunk" in event:
                    continue
                yield event
                continue

            if "message_chunk" in event:
                if "messages" in requested_modes:
                    yield (
                        "messages",
                        (
                            event["message_chunk"],
                            {"langgraph_node": "agent"},
                        ),
                    )
                    emitted_live_agent_chunks = True
                continue

            if "messages" in requested_modes and "agent" in event:
                if not emitted_live_agent_chunks:
                    for msg in event["agent"].get("messages", []):
                        if not isinstance(msg, AIMessage):
                            continue
                        yield (
                            "messages",
                            (
                                AIMessageChunk(**msg.model_dump(exclude={"type"})),
                                {"langgraph_node": "agent"},
                            ),
                        )
                emitted_live_agent_chunks = False

            if "updates" in requested_modes:
                yield ("updates", event)

    async def ainvoke(
        self,
        input: dict,
        config: dict | None = None,
        stream_mode: str = "updates",
    ) -> dict[str, Any]:
        """Drain query and return messages plus explicit terminal state."""
        drained_messages: list[Any] = []
        terminal: TerminalState | None = None
        transition: ContinueState | None = None

        # @@@ainvoke-drains-astream
        # QueryLoop is generator-first. ainvoke exists only as a compatibility
        # adapter for callers like LeonAgent.invoke/ainvoke and must not invent
        # a separate execution path.
        async for event in self.query(input, config=config):
            if "terminal" in event:
                terminal = event["terminal"]
                transition = event.get("transition")
                continue
            for section in ("agent", "tools"):
                drained_messages.extend(event.get(section, {}).get("messages", []))

        return {
            "messages": drained_messages,
            "reason": terminal.reason.value if terminal else TerminalReason.completed.value,
            "terminal": terminal,
            "transition": transition,
        }

    async def aget_state(self, config: dict | None = None) -> Any:
        """Minimal graph-state bridge for backend/web callers."""
        config = config or {}
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        if self._is_runtime_active():
            # @@@active-state-no-clobber - caller surfaces like /permissions and
            # /history can poll during an active run. Rehydrating from stale
            # checkpoint here would erase live thread-scoped permission state.
            values = self._snapshot_live_thread_state(thread_id)
            return SimpleNamespace(values=values)
        values = await self._hydrate_thread_state_from_checkpoint(thread_id)
        return SimpleNamespace(values=values)

    async def aupdate_state(
        self,
        config: dict | None,
        input_data: dict[str, Any] | None,
        as_node: str | None = None,
    ) -> Any:
        """Minimal graph-state update bridge for resumed-thread callers."""
        config = config or {}
        input_data = input_data or {}
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        messages = await self._load_messages(thread_id)
        raw_updates = input_data.get("messages", [])

        # @@@ql-06-state-bridge - backend/web still speaks the old graph-state
        # contract. Only the live caller shapes are supported here: append
        # resumed start messages, or apply RemoveMessage-based repairs before
        # appending replacement messages.
        if as_node == "__start__":
            messages.extend(self._parse_input({"messages": raw_updates}))
        else:
            updates = raw_updates if isinstance(raw_updates, list) else [raw_updates]
            remove_ids = {
                update.id
                for update in updates
                if isinstance(update, RemoveMessage) and getattr(update, "id", None)
            }
            if remove_ids:
                messages = [
                    message
                    for message in messages
                    if getattr(message, "id", None) not in remove_ids
                ]
            messages.extend(
                update
                for update in updates
                if not isinstance(update, RemoveMessage)
            )

        await self._save_messages(thread_id, messages)
        current_turn_count = self._app_state.turn_count if self._app_state is not None else 0
        self._sync_app_state(messages=messages, turn_count=current_turn_count)
        self._restore_discovered_tool_names_from_messages(thread_id, messages)
        return await self.aget_state(config)

    async def apersist_state(self, thread_id: str) -> None:
        """Persist the current thread-scoped loop/app state to the checkpointer."""
        messages = list(self._app_state.messages) if self._app_state is not None else await self._load_messages(thread_id)
        await self._save_messages(thread_id, messages)

    # -------------------------------------------------------------------------
    # Model invocation through middleware chain
    # -------------------------------------------------------------------------

    async def _invoke_model(
        self,
        messages: list,
        config: dict,
        *,
        thread_id: str = "default",
        max_output_tokens_override: int | None = None,
    ) -> ModelResponse:
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

            if max_output_tokens_override is not None and hasattr(bound, "bind"):
                try:
                    bound = bound.bind(max_tokens=max_output_tokens_override)
                except Exception:
                    pass

            # Build message list: system + conversation
            call_messages = []
            if request.system_message:
                call_messages.append(request.system_message)
            call_messages.extend(request.messages)

            result = await bound.ainvoke(call_messages)
            if not isinstance(result, list):
                result = [result]
            return ModelResponse(result=result, request_messages=list(request.messages))

        # Build ModelRequest
        inline_schemas = self._registry.get_inline_schemas(
            self._get_discovered_tool_names(thread_id)
        )
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

    def _bind_model(
        self,
        model: Any,
        tools: list | None,
        *,
        max_output_tokens_override: int | None = None,
    ) -> Any:
        if tools:
            try:
                bound = model.bind_tools(tools)
            except Exception:
                bound = model
        else:
            bound = model

        if max_output_tokens_override is not None and hasattr(bound, "bind"):
            try:
                bound = bound.bind(max_tokens=max_output_tokens_override)
            except Exception:
                pass
        return bound

    def _can_stream_tools(self) -> bool:
        stream_fn = getattr(self.model, "astream", None)
        if not callable(stream_fn):
            return False
        return type(self.model).__module__ != "unittest.mock"

    async def _prepare_streaming_request(
        self,
        messages: list,
        *,
        thread_id: str,
    ) -> ModelRequest:
        inline_schemas = self._registry.get_inline_schemas(
            self._get_discovered_tool_names(thread_id)
        )
        request = ModelRequest(
            model=self.model,
            messages=messages,
            system_message=self.system_prompt,
            tools=inline_schemas,
        )

        async def prepare_handler(request: ModelRequest) -> ModelResponse:
            return ModelResponse(
                result=[],
                request_messages=list(request.messages),
                prepared_request=request,
            )

        handler = prepare_handler
        for mw in reversed(self.middleware):
            if _mw_overrides_model_call(mw):
                handler = _make_model_wrapper(mw, handler)

        response = await handler(request)
        return response.prepared_request or request

    async def _stream_model_with_tool_overlap(
        self,
        messages: list,
        config: dict,
        *,
        thread_id: str,
        tool_context: ToolUseContext | None,
        max_output_tokens_override: int | None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        prepared_request = await self._prepare_streaming_request(messages, thread_id=thread_id)
        bound = self._bind_model(
            prepared_request.model,
            prepared_request.tools,
            max_output_tokens_override=max_output_tokens_override,
        )

        call_messages = []
        if prepared_request.system_message:
            call_messages.append(prepared_request.system_message)
        call_messages.extend(prepared_request.messages)

        executor = _StreamingToolExecutor(loop=self, tool_context=tool_context)
        aggregate: AIMessageChunk | None = None
        seen_tool_ids: set[str] = set()
        streamed_tool_calls: list[dict[str, Any]] = []

        try:
            async for chunk in bound.astream(call_messages):
                if isinstance(chunk, AIMessage):
                    chunk = AIMessageChunk(**chunk.model_dump(exclude={"type"}))
                elif not isinstance(chunk, AIMessageChunk):
                    continue

                # @@@stream-chunk-snapshot
                # Some providers reuse and mutate the same chunk object across
                # yields. Snapshot before yielding/aggregating so the final
                # AIMessage cannot collapse to the last empty chunk.
                chunk = AIMessageChunk(**chunk.model_dump(exclude={"type"}))
                if (
                    aggregate is not None
                    and getattr(chunk, "chunk_position", None) == "last"
                    and not chunk.content
                    and not getattr(chunk, "tool_calls", None)
                    and not getattr(chunk, "invalid_tool_calls", None)
                    and not getattr(chunk, "tool_call_chunks", None)
                    and getattr(chunk, "usage_metadata", None) == getattr(aggregate, "usage_metadata", None)
                ):
                    chunk = chunk.model_copy(update={"usage_metadata": None})
                aggregate = chunk if aggregate is None else aggregate + chunk

                yield {"type": "message_chunk", "chunk": chunk}

                tool_call_chunks = getattr(aggregate, "tool_call_chunks", None) or []
                for tool_call in getattr(aggregate, "tool_calls", None) or []:
                    ready_tool_call = self._normalize_stream_tool_call(tool_call, tool_call_chunks)
                    if ready_tool_call is None:
                        continue
                    call_id = ready_tool_call.get("id")
                    if not call_id or call_id in seen_tool_ids:
                        continue
                    seen_tool_ids.add(call_id)
                    streamed_tool_calls.append(ready_tool_call)
                    await executor.add_tool(ready_tool_call)

                completed = await executor.get_completed_results()
                if completed:
                    yield {"type": "tools", "messages": completed}
        except Exception:
            discarded = await executor.discard(reason="streaming_error")
            if discarded:
                yield {"type": "tools", "messages": discarded}
            raise

        if aggregate is None:
            raise RuntimeError("streaming model returned no AIMessageChunk")

        ai_message = AIMessage(**aggregate.model_dump(exclude={"type"}))
        self._notify_stream_response(prepared_request, ai_message)
        remaining = await executor.drain_remaining()
        yield {
            "type": "done",
            "response": ModelResponse(result=[ai_message], request_messages=list(prepared_request.messages)),
            "ai_message": ai_message,
            "tool_calls": list(streamed_tool_calls),
            "remaining_tool_results": remaining,
        }

    def _notify_stream_response(self, request: ModelRequest, ai_message: AIMessage) -> None:
        req_dict = {"messages": request.messages}
        resp_dict = {"messages": [ai_message]}
        for mw in self.middleware:
            dispatch = getattr(mw, "_dispatch_monitors", None)
            if callable(dispatch):
                dispatch("on_response", req_dict, resp_dict)

    async def _build_query_messages(self, messages: list, config: dict) -> tuple[list, list]:
        return await self._apply_before_model(list(messages), config)

    async def _apply_before_model(self, messages: list, config: dict) -> tuple[list, list]:
        """Run middleware before_model/abefore_model hooks on the live path."""
        current_messages = list(messages)
        injected_messages: list[Any] = []
        state = {"messages": current_messages}

        for mw in self.middleware:
            update: dict[str, Any] | None = None
            abefore = getattr(mw, "abefore_model", None)
            before = getattr(mw, "before_model", None)

            if callable(abefore):
                update = await abefore(state=state, runtime=None, config=config)
            elif callable(before):
                update = before(state=state, runtime=None, config=config)

            if not update:
                continue

            new_messages = update.get("messages")
            if new_messages:
                if not isinstance(new_messages, list):
                    new_messages = [new_messages]
                current_messages.extend(new_messages)
                injected_messages.extend(new_messages)
                state["messages"] = current_messages

        return current_messages, injected_messages

    def _sync_app_state(self, messages: list, turn_count: int) -> None:
        """Keep runtime AppState aligned with the loop's live state."""
        if self._app_state is None:
            return

        snapshot = list(messages)
        current_cost = self._read_runtime_cost()
        bootstrap_cost = self._bootstrap.total_cost_usd if self._bootstrap is not None else 0.0
        cumulative_cost = max(current_cost, self._app_state.total_cost, bootstrap_cost)
        compact_boundary_index = self._read_compact_boundary_index()

        # @@@sa-03-cost-accumulator-monotonic
        # /clear must preserve session accumulators, so loop sync cannot let a
        # lower per-run observation overwrite the accumulated session total.
        if self._bootstrap is not None:
            self._bootstrap.total_cost_usd = cumulative_cost

        # @@@app-state-sync
        # ql-02 needs the loop's local lifecycle to write back into AppState,
        # but we still do not have compaction yet. Clamp the boundary so the
        # store stays coherent without pretending compaction exists.
        def _update(state: AppState) -> AppState:
            return state.model_copy(
                update={
                    "messages": snapshot,
                    "turn_count": turn_count,
                    "total_cost": cumulative_cost,
                    "compact_boundary_index": compact_boundary_index,
                }
            )

        self._app_state.set_state(_update)

    def _read_runtime_cost(self) -> float:
        if self._runtime is None:
            return self._app_state.total_cost if self._app_state is not None else 0.0
        try:
            return float(self._runtime.cost)
        except Exception:
            return self._app_state.total_cost if self._app_state is not None else 0.0

    def _read_compact_boundary_index(self) -> int:
        if self._memory_middleware is None:
            return 0
        try:
            boundary = int(self._memory_middleware.compact_boundary_index)
        except Exception:
            return 0
        return max(boundary, 0)

    def _get_discovered_tool_names(self, thread_id: str) -> set[str]:
        # @@@dt-03-thread-scoped-deferred-tools - deferred discovery must stay
        # isolated per thread_id, or one thread's tool_search silently changes
        # another thread's inline schema surface on the next turn.
        return self._tool_discovered_tool_names_by_thread.setdefault(thread_id, set())

    def _restore_discovered_tool_names_from_messages(
        self,
        thread_id: str,
        messages: list,
    ) -> None:
        discovered: set[str] = set()
        for message in messages:
            if not isinstance(message, ToolMessage) or getattr(message, "name", None) != "tool_search":
                continue
            content = getattr(message, "content", None)
            if not isinstance(content, str):
                continue
            try:
                payload = json.loads(content)
            except Exception:
                continue
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not isinstance(name, str):
                    continue
                entry = self._registry.get(name)
                if entry is not None and entry.mode == ToolMode.DEFERRED:
                    discovered.add(name)
        self._tool_discovered_tool_names_by_thread[thread_id] = discovered

    def _build_tool_use_context(self, messages: list, *, thread_id: str = "default") -> ToolUseContext | None:
        if self._bootstrap is None or self._app_state is None:
            return None
        has_permission_resolver = self._bootstrap.permission_resolver_scope != "none"
        return ToolUseContext(
            bootstrap=self._bootstrap,
            get_app_state=self._app_state.get_state,
            set_app_state=self._app_state.set_state,
            refresh_tools=self._refresh_tools,
            can_use_tool=lambda name, args, permission_context, request: self._default_can_use_tool(
                name=name,
                permission_context=permission_context,
            ),
            request_permission=(
                lambda name, args, context, request, message: self._request_permission(
                    thread_id=thread_id,
                    name=name,
                    args=args,
                    message=message,
                )
            )
            if has_permission_resolver
            else None,
            consume_permission_resolution=lambda name, args, context, request: self._consume_permission_resolution(
                thread_id=thread_id,
                name=name,
                args=args,
            ),
            read_file_state=self._tool_read_file_state,
            loaded_nested_memory_paths=self._tool_loaded_nested_memory_paths,
            discovered_skill_names=self._tool_discovered_skill_names,
            discovered_tool_names=self._get_discovered_tool_names(thread_id),
            nested_memory_attachment_triggers=set(),
            abort_controller=self._tool_abort_controller,
            messages=list(messages),
            thread_id=thread_id,
        )

    def _default_can_use_tool(
        self,
        *,
        name: str,
        permission_context: ToolPermissionContext,
    ) -> dict[str, Any] | None:
        if self._app_state is None:
            return None
        permission_state = self._app_state.tool_permission_context
        merged_context = ToolPermissionContext(
            is_read_only=permission_context.is_read_only,
            is_destructive=permission_context.is_destructive,
            alwaysAllowRules=permission_state.alwaysAllowRules,
            alwaysDenyRules=permission_state.alwaysDenyRules,
            alwaysAskRules=permission_state.alwaysAskRules,
            allowManagedPermissionRulesOnly=permission_state.allowManagedPermissionRulesOnly,
        )
        decision = evaluate_permission_rules(name, merged_context)
        if (
            decision is not None
            and decision.get("decision") == "ask"
            and self._bootstrap is not None
            and self._bootstrap.permission_resolver_scope == "none"
        ):
            # @@@permission-headless-fail-loud - ask is only a real product mode
            # when this run has an owner-facing resolver. Otherwise fail loudly
            # instead of creating a dead-end pending request in hidden state.
            return {
                "decision": "deny",
                "message": f"{decision.get('message')}. No interactive permission resolver is available for this run.",
            }
        return decision

    def _request_permission(
        self,
        *,
        thread_id: str,
        name: str,
        args: dict[str, Any],
        message: str | None,
    ) -> str | None:
        if self._app_state is None:
            return None

        request_id = uuid.uuid4().hex[:8]
        payload = {
            "request_id": request_id,
            "thread_id": thread_id,
            "tool_name": name,
            "args": copy.deepcopy(args),
            "message": message,
        }

        def _store(state: AppState) -> AppState:
            pending = dict(state.pending_permission_requests)
            pending[request_id] = payload
            return state.model_copy(update={"pending_permission_requests": pending})

        self._app_state.set_state(_store)
        return request_id

    def _consume_permission_resolution(
        self,
        *,
        thread_id: str,
        name: str,
        args: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self._app_state is None:
            return None

        resolved_items = list(self._app_state.resolved_permission_requests.items())
        matched_id: str | None = None
        matched_payload: dict[str, Any] | None = None
        for request_id, payload in resolved_items:
            if payload.get("thread_id") != thread_id:
                continue
            if payload.get("tool_name") != name:
                continue
            if payload.get("args") != args:
                continue
            matched_id = request_id
            matched_payload = payload
            break

        if matched_id is None or matched_payload is None:
            return None

        def _consume(state: AppState) -> AppState:
            resolved = dict(state.resolved_permission_requests)
            resolved.pop(matched_id, None)
            return state.model_copy(update={"resolved_permission_requests": resolved})

        self._app_state.set_state(_consume)
        return {
            "decision": matched_payload.get("decision"),
            "message": matched_payload.get("message"),
        }

    def _sync_tool_context_messages(
        self,
        tool_context: ToolUseContext | None,
        messages: list,
    ) -> None:
        if tool_context is None:
            return
        tool_context.messages = list(messages)

    async def _refresh_tools_between_turns(self, tool_context: ToolUseContext | None) -> None:
        refresh = self._refresh_tools
        if refresh is None and tool_context is not None:
            refresh = tool_context.refresh_tools
        if refresh is None:
            return
        result = refresh()
        if inspect.isawaitable(result):
            await result

    async def _handle_model_error_recovery(
        self,
        *,
        exc: Exception,
        thread_id: str,
        messages: list,
        turn: int,
        transition: ContinueState | None,
        max_output_tokens_recovery_count: int,
        has_attempted_reactive_compact: bool,
        max_output_tokens_override: int | None,
        transient_api_retry_count: int,
    ) -> dict[str, Any] | None:
        error_message = str(exc)
        error_text = error_message.lower()

        parsed_overflow = self._parse_context_overflow_override(error_message)
        if parsed_overflow is not None:
            return {
                "messages": messages,
                "transition": ContinueState(reason=ContinueReason.max_output_tokens_escalate),
                "max_output_tokens_recovery_count": max_output_tokens_recovery_count,
                "has_attempted_reactive_compact": has_attempted_reactive_compact,
                "max_output_tokens_override": parsed_overflow,
                "transient_api_retry_count": transient_api_retry_count,
                "terminal": None,
            }

        if self._is_transient_api_error(exc, error_text):
            if transient_api_retry_count >= _TRANSIENT_API_MAX_RETRIES:
                return None
            delay_seconds = self._retry_delay_seconds(exc, transient_api_retry_count)
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            return {
                "messages": messages,
                "transition": ContinueState(reason=ContinueReason.api_retry),
                "max_output_tokens_recovery_count": max_output_tokens_recovery_count,
                "has_attempted_reactive_compact": has_attempted_reactive_compact,
                "max_output_tokens_override": max_output_tokens_override,
                "transient_api_retry_count": transient_api_retry_count + 1,
                "terminal": None,
            }

        if "max_output_tokens" in error_text:
            if max_output_tokens_override is None:
                return {
                    "messages": messages,
                    "transition": ContinueState(reason=ContinueReason.max_output_tokens_escalate),
                    "max_output_tokens_recovery_count": max_output_tokens_recovery_count,
                    "has_attempted_reactive_compact": has_attempted_reactive_compact,
                    "max_output_tokens_override": _ESCALATED_MAX_OUTPUT_TOKENS,
                    "transient_api_retry_count": transient_api_retry_count,
                    "terminal": None,
                }
            if max_output_tokens_recovery_count < 3:
                recovered_messages = list(messages)
                recovered_messages.append(
                    HumanMessage(
                        content="Output token limit hit. Resume directly with no apology or recap.",
                    )
                )
                return {
                    "messages": recovered_messages,
                    "transition": ContinueState(reason=ContinueReason.max_output_tokens_recovery),
                    "max_output_tokens_recovery_count": max_output_tokens_recovery_count + 1,
                    "has_attempted_reactive_compact": has_attempted_reactive_compact,
                    "max_output_tokens_override": max_output_tokens_override,
                    "transient_api_retry_count": transient_api_retry_count,
                    "terminal": None,
                }
            return {
                "messages": messages,
                "transition": ContinueState(reason=ContinueReason.max_output_tokens_recovery),
                "max_output_tokens_recovery_count": max_output_tokens_recovery_count,
                "has_attempted_reactive_compact": has_attempted_reactive_compact,
                "max_output_tokens_override": max_output_tokens_override,
                "transient_api_retry_count": transient_api_retry_count,
                "terminal": TerminalState(
                    reason=TerminalReason.model_error,
                    turn_count=turn,
                    error=str(exc),
                ),
            }

        if self._is_prompt_too_long_error(error_text):
            if transition is None or transition.reason is not ContinueReason.collapse_drain_retry:
                drained = await self._recover_from_overflow(messages)
                if drained is not None and drained["committed"] > 0:
                    return {
                        "messages": drained["messages"],
                        "transition": ContinueState(reason=ContinueReason.collapse_drain_retry),
                        "max_output_tokens_recovery_count": max_output_tokens_recovery_count,
                        "has_attempted_reactive_compact": has_attempted_reactive_compact,
                        "max_output_tokens_override": max_output_tokens_override,
                        "transient_api_retry_count": transient_api_retry_count,
                        "terminal": None,
                    }
            if not has_attempted_reactive_compact:
                compacted = await self._force_reactive_compact(messages, thread_id=thread_id)
                if compacted is not None:
                    return {
                        "messages": compacted,
                        "transition": ContinueState(reason=ContinueReason.reactive_compact_retry),
                        "max_output_tokens_recovery_count": max_output_tokens_recovery_count,
                        "has_attempted_reactive_compact": True,
                        "max_output_tokens_override": max_output_tokens_override,
                        "transient_api_retry_count": transient_api_retry_count,
                        "terminal": None,
                    }
            return {
                "messages": messages,
                "transition": transition,
                "max_output_tokens_recovery_count": max_output_tokens_recovery_count,
                "has_attempted_reactive_compact": has_attempted_reactive_compact,
                "max_output_tokens_override": max_output_tokens_override,
                "transient_api_retry_count": transient_api_retry_count,
                "terminal": TerminalState(
                    reason=TerminalReason.prompt_too_long,
                    turn_count=turn,
                    error=str(exc),
                ),
            }

        return None

    @staticmethod
    def _parse_context_overflow_override(error_message: str) -> int | None:
        match = re.search(
            r"input length and `max_tokens` exceed context limit: (\d+) \+ (\d+) > (\d+)",
            error_message,
        )
        if match is None:
            return None
        input_tokens = int(match.group(1))
        context_limit = int(match.group(3))
        available_context = max(0, context_limit - input_tokens - _CONTEXT_OVERFLOW_SAFETY_BUFFER)
        if available_context < _FLOOR_OUTPUT_TOKENS:
            return None
        return max(_FLOOR_OUTPUT_TOKENS, available_context)

    @staticmethod
    def _is_transient_api_error(exc: Exception, error_text: str) -> bool:
        status = getattr(exc, "status", None)
        return status in {429, 529} or '"type":"overloaded_error"' in error_text

    @staticmethod
    def _retry_delay_seconds(exc: Exception, transient_api_retry_count: int) -> float:
        headers = getattr(exc, "headers", None) or {}
        # @@@retry-after-shape
        # Test doubles use plain dict headers while SDK errors expose a Headers-like
        # object. Keep this probe shape-tolerant so the loop can honor retry-after
        # without forcing a specific exception class.
        if hasattr(headers, "get"):
            retry_after = headers.get("retry-after")
        else:
            retry_after = None
        try:
            if retry_after is not None:
                return max(0.0, float(retry_after))
        except (TypeError, ValueError):
            pass
        return _TRANSIENT_API_BASE_DELAY_SECONDS * (2**transient_api_retry_count)

    def _handle_truncated_response_recovery(
        self,
        *,
        ai_msg: AIMessage,
        messages: list,
        turn: int,
        max_output_tokens_recovery_count: int,
        max_output_tokens_override: int | None,
    ) -> dict[str, Any] | None:
        if not self._is_max_output_truncated(ai_msg):
            return None

        if max_output_tokens_override is None:
            return {
                "messages": messages,
                "transition": ContinueState(reason=ContinueReason.max_output_tokens_escalate),
                "max_output_tokens_recovery_count": max_output_tokens_recovery_count,
                "max_output_tokens_override": _ESCALATED_MAX_OUTPUT_TOKENS,
                "yield_ai": False,
                "terminal": None,
            }

        if max_output_tokens_recovery_count < 3:
            recovered_messages = list(messages)
            recovered_messages.append(ai_msg)
            recovered_messages.append(
                HumanMessage(
                    content="Output token limit hit. Resume directly with no apology or recap.",
                )
            )
            return {
                "messages": recovered_messages,
                "transition": ContinueState(reason=ContinueReason.max_output_tokens_recovery),
                "max_output_tokens_recovery_count": max_output_tokens_recovery_count + 1,
                "max_output_tokens_override": max_output_tokens_override,
                "yield_ai": False,
                "terminal": None,
            }

        surfaced_messages = list(messages)
        surfaced_messages.append(ai_msg)
        return {
            "messages": surfaced_messages,
            "transition": ContinueState(reason=ContinueReason.max_output_tokens_recovery),
            "max_output_tokens_recovery_count": max_output_tokens_recovery_count,
            "max_output_tokens_override": max_output_tokens_override,
            "yield_ai": True,
            "terminal": TerminalState(
                reason=TerminalReason.model_error,
                turn_count=turn,
                error="max_output_tokens",
            ),
        }

    async def _force_reactive_compact(self, messages: list, *, thread_id: str) -> list | None:
        if self._memory_middleware is None:
            return None
        compact = getattr(self._memory_middleware, "compact_messages_for_recovery", None)
        if not callable(compact):
            return None
        signature = inspect.signature(compact)
        if "thread_id" in signature.parameters:
            return await compact(messages, thread_id=thread_id)
        return await compact(messages)

    async def _recover_from_overflow(self, messages: list) -> dict[str, Any] | None:
        # @@@collapse-drain-single-shot
        # ql-04 needs collapse-drain and reactive-compact to stay as separate
        # phases. The drain hook is optional, but if present it only gets one
        # chance before prompt-too-long falls through to reactive compaction.
        for middleware in self.middleware:
            recover = getattr(middleware, "recover_from_overflow", None)
            if not callable(recover):
                continue
            drained = recover(messages)
            if inspect.isawaitable(drained):
                drained = await drained
            if drained is None:
                return None
            committed = int(getattr(drained, "get", lambda *_: 0)("committed", 0))
            updated_messages = getattr(drained, "get", lambda *_: None)("messages")
            if committed <= 0 or not isinstance(updated_messages, list):
                return None
            return {"committed": committed, "messages": list(updated_messages)}
        return None

    @staticmethod
    def _is_prompt_too_long_error(error_text: str) -> bool:
        return (
            "prompt is too long" in error_text
            or "prompt too long" in error_text
            or "context length" in error_text
            or "maximum context length" in error_text
        )

    @staticmethod
    def _is_max_output_truncated(message: AIMessage) -> bool:
        response_metadata = getattr(message, "response_metadata", None) or {}
        additional_kwargs = getattr(message, "additional_kwargs", None) or {}
        finish_reason = (
            response_metadata.get("finish_reason")
            or response_metadata.get("stop_reason")
            or additional_kwargs.get("finish_reason")
            or additional_kwargs.get("stop_reason")
        )
        return finish_reason in {"length", "max_tokens", "max_output_tokens"}

    # -------------------------------------------------------------------------
    # Tool execution through middleware chain
    # -------------------------------------------------------------------------

    async def _execute_tools(
        self,
        tool_calls: list,
        model_response: ModelResponse,
        tool_context: ToolUseContext | None,
    ) -> list[ToolMessage]:
        """Execute tool calls respecting concurrency safety, via middleware chain."""
        results: dict[int, ToolMessage] = {}

        async def execute_batch(batch: list[tuple[int, dict]]) -> None:
            if not batch:
                return
            batch_results = await asyncio.gather(
                *[self._execute_single_tool(tool_call, tool_context) for _, tool_call in batch],
                return_exceptions=True,
            )
            for (idx, tool_call), result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    results[idx] = ToolMessage(
                        content=f"<tool_use_error>{result}</tool_use_error>",
                        tool_call_id=tool_call.get("id", ""),
                        name=tool_call.get("name", ""),
                    )
                    continue
                results[idx] = result

        safe_batch: list[tuple[int, dict]] = []
        for idx, tool_call in enumerate(tool_calls):
            # @@@tool-order-boundary
            # te-01 needs the non-streaming path to keep the same queue barrier
            # semantics as the streaming executor: contiguous safe tools may fan
            # out together, but any unsafe tool flushes the batch and blocks the
            # next safe tool until it finishes.
            if self._tool_is_concurrency_safe(tool_call):
                safe_batch.append((idx, tool_call))
                continue

            await execute_batch(safe_batch)
            safe_batch = []
            try:
                results[idx] = await self._execute_single_tool(tool_call, tool_context)
            except Exception as exc:
                results[idx] = ToolMessage(
                    content=f"<tool_use_error>{exc}</tool_use_error>",
                    tool_call_id=tool_call.get("id", ""),
                    name=tool_call.get("name", ""),
                )

        await execute_batch(safe_batch)
        return [results[i] for i in range(len(tool_calls))]

    async def _execute_single_tool(
        self,
        tool_call: dict,
        tool_context: ToolUseContext | None,
    ) -> ToolMessage:
        name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
        call_id = tool_call.get("id", "")
        args = tool_call.get("args", {}) or tool_call.get("function", {}).get("arguments", {})

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
            state=tool_context,
            runtime=self._runtime,  # type: ignore[arg-type]
        )

        async def innermost_tool_handler(req: ToolCallRequest) -> ToolMessage:
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

        tool_handler = innermost_tool_handler
        for mw in reversed(self.middleware):
            if _mw_overrides_tool_call(mw):
                tool_handler = _make_tool_wrapper(mw, tool_handler)

        return await tool_handler(tc_request)

    def _tool_is_concurrency_safe(self, tool_call: dict) -> bool:
        name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
        entry = self._registry.get(name)
        if entry is None:
            return False
        safety = entry.is_concurrency_safe
        if callable(safety):
            args = tool_call.get("args", {})
            if isinstance(args, str):
                try:
                    import json as _json
                    args = _json.loads(args)
                except Exception:
                    args = {}
            try:
                return bool(safety(args if isinstance(args, dict) else {}))
            except Exception:
                return False
        return bool(safety)

    def _tool_call_is_ready(self, tool_call: dict) -> bool:
        name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
        entry = self._registry.get(name)
        if entry is None:
            return True

        args = tool_call.get("args", {})
        if isinstance(args, str):
            try:
                import json as _json

                args = _json.loads(args)
            except Exception:
                return False
        if not isinstance(args, dict):
            return False

        schema = entry.get_schema() or {}
        parameters = schema.get("parameters", {}) if isinstance(schema, dict) else {}
        return _required_sets_match(parameters, args) if isinstance(parameters, dict) else True

    def _normalize_stream_tool_call(
        self,
        tool_call: dict,
        tool_call_chunks: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        call_id = tool_call.get("id")
        name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
        args: Any = tool_call.get("args", {})
        if isinstance(args, str):
            try:
                import json as _json

                args = _json.loads(args)
            except Exception:
                args = {}

        for chunk in tool_call_chunks:
            if chunk.get("id") != call_id:
                continue
            if chunk.get("name"):
                name = chunk["name"]
            raw_args = chunk.get("args")
            if raw_args in (None, ""):
                continue
            if isinstance(raw_args, str):
                try:
                    import json as _json

                    args = _json.loads(raw_args)
                except Exception:
                    continue
            else:
                args = raw_args

        normalized = {"name": name, "args": args, "id": call_id}
        if not self._tool_call_is_ready(normalized):
            return None
        return normalized

    # -------------------------------------------------------------------------
    # Checkpointer persistence
    # -------------------------------------------------------------------------

    async def _load_messages(self, thread_id: str) -> list:
        """Load message history from checkpointer (if available)."""
        channel_values = await self._load_checkpoint_channel_values(thread_id)
        return list(channel_values.get("messages", []))

    async def _load_checkpoint_channel_values(self, thread_id: str) -> dict[str, Any]:
        """Load raw channel values for one thread checkpoint."""
        if self.checkpointer is None:
            return {}
        try:
            cfg = self._checkpoint_config(thread_id)
            checkpoint = await self.checkpointer.aget(cfg)
            if checkpoint is None:
                return {}
            return dict(checkpoint.get("channel_values", {}) or {})
        except Exception:
            logger.debug("QueryLoop: could not load checkpoint for thread %s", thread_id)
            return {}

    def _thread_permission_state_snapshot(
        self,
        thread_id: str,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        if self._app_state is None:
            return {}, {}, {}

        permission_context = copy.deepcopy(self._app_state.tool_permission_context.model_dump())
        pending = {
            key: copy.deepcopy(value)
            for key, value in self._app_state.pending_permission_requests.items()
            if value.get("thread_id") == thread_id
        }
        resolved = {
            key: copy.deepcopy(value)
            for key, value in self._app_state.resolved_permission_requests.items()
            if value.get("thread_id") == thread_id
        }
        return permission_context, pending, resolved

    def _thread_memory_state_snapshot(self, thread_id: str) -> dict[str, Any]:
        if self._memory_middleware is None:
            return {}
        snapshot = getattr(self._memory_middleware, "snapshot_thread_state", None)
        if not callable(snapshot):
            return {}
        return dict(snapshot(thread_id) or {})

    def _is_runtime_active(self) -> bool:
        current_state = getattr(self._runtime, "current_state", None)
        return getattr(current_state, "value", current_state) == "active"

    def _snapshot_live_thread_state(self, thread_id: str) -> dict[str, Any]:
        messages = list(self._app_state.messages) if self._app_state is not None else []
        permission_context, pending, resolved = self._thread_permission_state_snapshot(thread_id)
        memory_state = self._thread_memory_state_snapshot(thread_id)
        return {
            "messages": messages,
            "tool_permission_context": permission_context,
            "pending_permission_requests": pending,
            "resolved_permission_requests": resolved,
            "memory_compaction_state": memory_state,
        }

    def _restore_thread_permission_state(
        self,
        thread_id: str,
        *,
        permission_context: dict[str, Any],
        pending: dict[str, dict[str, Any]],
        resolved: dict[str, dict[str, Any]],
    ) -> None:
        if self._app_state is None:
            return

        # @@@permission-checkpoint-bridge - pending/resolved permission requests
        # are thread-scoped runtime state, not display-only metadata. They must
        # survive checkpoint replay so backend/UI surfaces stay honest after an
        # idle reload or agent recreation.
        def _update(state: AppState) -> AppState:
            kept_pending = {
                key: value
                for key, value in state.pending_permission_requests.items()
                if value.get("thread_id") != thread_id
            }
            kept_pending.update(copy.deepcopy(pending))
            kept_resolved = {
                key: value
                for key, value in state.resolved_permission_requests.items()
                if value.get("thread_id") != thread_id
            }
            kept_resolved.update(copy.deepcopy(resolved))
            return state.model_copy(
                update={
                    "tool_permission_context": ToolPermissionState.model_validate(copy.deepcopy(permission_context)),
                    "pending_permission_requests": kept_pending,
                    "resolved_permission_requests": kept_resolved,
                }
            )

        self._app_state.set_state(_update)

    def _restore_thread_memory_state(
        self,
        thread_id: str,
        *,
        memory_state: dict[str, Any],
    ) -> None:
        if self._memory_middleware is None:
            return
        restore = getattr(self._memory_middleware, "restore_thread_state", None)
        if callable(restore):
            restore(thread_id, memory_state)

    async def _hydrate_thread_state_from_checkpoint(self, thread_id: str) -> dict[str, Any]:
        channel_values = await self._load_checkpoint_channel_values(thread_id)
        messages = list(channel_values.get("messages", []))
        permission_context = dict(channel_values.get("tool_permission_context", {}) or {})
        pending = dict(channel_values.get("pending_permission_requests", {}) or {})
        resolved = dict(channel_values.get("resolved_permission_requests", {}) or {})
        memory_state = dict(channel_values.get("memory_compaction_state", {}) or {})
        turn_count = self._app_state.turn_count if self._app_state is not None else 0
        self._sync_app_state(messages=messages, turn_count=turn_count)
        self._restore_thread_permission_state(
            thread_id,
            permission_context=permission_context,
            pending=pending,
            resolved=resolved,
        )
        self._restore_thread_memory_state(
            thread_id,
            memory_state=memory_state,
        )
        return {
            "messages": messages,
            "tool_permission_context": permission_context,
            "pending_permission_requests": pending,
            "resolved_permission_requests": resolved,
            "memory_compaction_state": memory_state,
        }

    async def _save_messages(self, thread_id: str, messages: list) -> None:
        """Persist message history to checkpointer."""
        if self.checkpointer is None:
            return
        try:
            from langgraph.checkpoint.base import CheckpointMetadata, empty_checkpoint

            cfg = self._checkpoint_config(thread_id)
            checkpoint = empty_checkpoint()
            permission_context, pending_requests, resolved_requests = self._thread_permission_state_snapshot(thread_id)
            memory_state = self._thread_memory_state_snapshot(thread_id)
            checkpoint["channel_values"] = {
                "messages": messages,
                "tool_permission_context": permission_context,
                "pending_permission_requests": pending_requests,
                "resolved_permission_requests": resolved_requests,
                "memory_compaction_state": memory_state,
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

    def _collect_memory_system_notices(self, pending_notices: list[HumanMessage]) -> None:
        if self._memory_middleware is None:
            return
        consume_many = getattr(self._memory_middleware, "consume_pending_notices", None)
        notices: list[dict[str, Any]] = []
        if callable(consume_many):
            notices = list(consume_many() or [])
        else:
            consume_one = getattr(self._memory_middleware, "consume_latest_compaction_notice", None)
            if callable(consume_one):
                notice = consume_one()
                if notice:
                    notices = [notice]
        for notice in notices:
            pending_notices.append(
                HumanMessage(
                    content=str(notice.get("content") or ""),
                    metadata={
                        "source": "system",
                        "notification_type": str(notice.get("notification_type") or "compact"),
                        "compact_boundary_index": int(notice.get("compact_boundary_index") or 0),
                    },
                )
            )

    def _append_system_notices(self, messages: list, notices: list[HumanMessage]) -> list:
        if not notices:
            return messages
        # @@@compact-notice-persist - compaction changes the model-visible
        # boundary, but the notice is for the owner surface only. Persist it
        # after the run settles so replay stays honest without perturbing the
        # same run's next model call.
        return list(messages) + list(notices)

    def _build_terminal_notice(self, terminal: TerminalState | None) -> HumanMessage | None:
        # @@@terminal-recovery-notice - recovery exhaustion must survive cold
        # rebuilds. Persist one owner-visible system notice instead of leaving
        # prompt-too-long as a hot-stream-only error.
        if terminal is None or terminal.reason is not TerminalReason.prompt_too_long:
            return None
        return HumanMessage(
            content=_PROMPT_TOO_LONG_NOTICE_TEXT,
            metadata={"source": "system"},
        )

    def _terminal_error_text(self, terminal: TerminalState) -> str:
        if terminal.reason is TerminalReason.prompt_too_long:
            return _PROMPT_TOO_LONG_NOTICE_TEXT
        return terminal.error or terminal.reason.value

    @staticmethod
    def _checkpoint_config(thread_id: str) -> dict[str, Any]:
        # @@@sa-03-real-checkpointer-config
        # AsyncSqliteSaver requires checkpoint_ns even when we only use a
        # single logical namespace; without it, aput() raises and replay dies.
        return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

    async def aclear(self, thread_id: str) -> None:
        """Clear turn-scoped state for a thread while preserving session accumulators."""
        await self._save_messages(thread_id, [])

        self._tool_read_file_state.clear()
        self._tool_loaded_nested_memory_paths.clear()
        self._tool_discovered_skill_names.clear()
        self._tool_discovered_tool_names_by_thread.pop(thread_id, None)

        if self._memory_middleware is not None:
            summary_store = getattr(self._memory_middleware, "summary_store", None)
            if summary_store is not None:
                # @@@clear-thread-clears-summary-store - api-05 requires /clear
                # to wipe replayable compaction state, not just in-memory cache.
                summary_store.delete_thread_summaries(thread_id)
            if hasattr(self._memory_middleware, "_cached_summary"):
                self._memory_middleware._cached_summary = None
            if hasattr(self._memory_middleware, "_summary_restored"):
                self._memory_middleware._summary_restored = False
            if hasattr(self._memory_middleware, "_summary_thread_id"):
                self._memory_middleware._summary_thread_id = None
            if hasattr(self._memory_middleware, "_compact_up_to_index"):
                self._memory_middleware._compact_up_to_index = 0
            clear_thread_state = getattr(self._memory_middleware, "clear_thread_state", None)
            if callable(clear_thread_state):
                clear_thread_state(thread_id)

        if self._app_state is not None:
            preserved_total_cost = self._app_state.total_cost
            preserved_tool_overrides = dict(self._app_state.tool_overrides)
            pending_requests = {
                key: value
                for key, value in self._app_state.pending_permission_requests.items()
                if value.get("thread_id") != thread_id
            }
            resolved_requests = {
                key: value
                for key, value in self._app_state.resolved_permission_requests.items()
                if value.get("thread_id") != thread_id
            }

            def _reset(state: AppState) -> AppState:
                return state.model_copy(
                    update={
                        "messages": [],
                        "turn_count": 0,
                        "total_cost": preserved_total_cost,
                        "compact_boundary_index": 0,
                        "tool_overrides": preserved_tool_overrides,
                        "pending_permission_requests": pending_requests,
                        "resolved_permission_requests": resolved_requests,
                    }
                )

            self._app_state.set_state(_reset)

        await self._save_messages(thread_id, [])

        if self._bootstrap is not None:
            old_session_id = self._bootstrap.session_id
            self._bootstrap.parent_session_id = old_session_id
            self._bootstrap.session_id = uuid.uuid4().hex

    # -------------------------------------------------------------------------
    # Input parsing
    # -------------------------------------------------------------------------

    @staticmethod
    def _parse_input(input: dict | None) -> list:
        """Convert input dict to list of LangChain message objects."""
        if input is None:
            return []
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

    @staticmethod
    def _ai_message_has_visible_content(message: AIMessage) -> bool:
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content.strip() != ""
        if isinstance(content, list):
            for item in content:
                if isinstance(item, str) and item.strip():
                    return True
                if isinstance(item, dict) and str(item.get("text", "")).strip():
                    return True
            return False
        return bool(content)

    @staticmethod
    def _get_terminal_followthrough_notice(messages: list[Any]) -> HumanMessage | None:
        if not messages:
            return None
        last_message = messages[-1]
        if last_message.__class__.__name__ != "HumanMessage":
            return None
        metadata = getattr(last_message, "metadata", None) or {}
        if metadata.get("source") != "system":
            return None
        if metadata.get("notification_type") not in {"agent", "command"}:
            return None
        content = getattr(last_message, "content", "")
        text = content if isinstance(content, str) else str(content)
        if "CommandNotification" not in text and "task-notification" not in text:
            return None
        return last_message

    @classmethod
    def _build_terminal_followthrough_fallback(cls, notice: HumanMessage) -> AIMessage:
        metadata = getattr(notice, "metadata", None) or {}
        notification_type = str(metadata.get("notification_type") or "task")
        content = getattr(notice, "content", "")
        text = content if isinstance(content, str) else str(content)
        status_match = re.search(r"<status>(.*?)</status>", text, flags=re.IGNORECASE | re.DOTALL)
        status = (status_match.group(1).strip().lower() if status_match else "")
        subject = "command" if notification_type == "command" else "agent"
        # @@@terminal-followthrough-fallback - terminal background notifications
        # must never collapse into notice-only durable history when the model
        # reentry stays silent; surface the silence explicitly instead.
        if status == "completed":
            reply = f"Background {subject} completed, but the followthrough assistant reply was empty."
        elif status == "cancelled":
            reply = f"Background {subject} was cancelled, but the followthrough assistant reply was empty."
        elif status == "error":
            reply = f"Background {subject} failed, but the followthrough assistant reply was empty."
        else:
            reply = f"Background {subject} update arrived, but the followthrough assistant reply was empty."
        return AIMessage(content=reply)


class _StreamingToolExecutor:
    def __init__(self, loop: QueryLoop, tool_context: ToolUseContext | None):
        self._loop = loop
        self._tool_context = tool_context
        self._tracked: list[_TrackedTool] = []
        self._discarded = False

    async def add_tool(self, tool_call: dict[str, Any]) -> None:
        if self._discarded:
            return
        name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
        if self._loop._registry.get(name) is None:
            self._tracked.append(
                _TrackedTool(
                    order=len(self._tracked),
                    tool_call=tool_call,
                    is_concurrency_safe=False,
                    status="completed",
                    result=self._tool_error(tool_call, f"Tool '{name}' not found"),
                )
            )
            return
        tracked = _TrackedTool(
            order=len(self._tracked),
            tool_call=tool_call,
            is_concurrency_safe=self._loop._tool_is_concurrency_safe(tool_call),
        )
        self._tracked.append(tracked)
        self._process_queue()

    async def get_completed_results(self) -> list[ToolMessage]:
        await asyncio.sleep(0)
        self._process_queue()
        ready: list[ToolMessage] = []
        for tracked in self._tracked:
            if tracked.status == "yielded":
                continue
            if tracked.status == "completed" and tracked.result is not None:
                tracked.status = "yielded"
                ready.append(tracked.result)
                continue
            break
        return ready

    async def drain_remaining(self) -> list[ToolMessage]:
        while True:
            self._process_queue()
            running = [tracked.task for tracked in self._tracked if tracked.status == "executing" and tracked.task is not None]
            if not running:
                break
            await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
        self._process_queue()
        remaining: list[ToolMessage] = []
        for tracked in self._tracked:
            if tracked.status == "yielded":
                continue
            if tracked.status == "completed" and tracked.result is not None:
                tracked.status = "yielded"
                remaining.append(tracked.result)
        return remaining

    async def discard(self, reason: str) -> list[ToolMessage]:
        # @@@streaming-tool-discard
        # ql-05 must not leave orphaned tool tasks behind when streaming exits
        # early. Synthetic error emission is still a later hardening pass, but
        # task cleanup itself must happen now.
        self._discarded = True
        running: list[asyncio.Task[ToolMessage]] = []
        for tracked in self._tracked:
            if tracked.status == "queued":
                tracked.status = "completed"
                tracked.result = self._synthetic_error(tracked.tool_call, reason)
                continue
            if tracked.status == "executing" and tracked.task is not None:
                tracked.task.cancel()
                running.append(tracked.task)
        if running:
            await asyncio.gather(*running, return_exceptions=True)
        for tracked in self._tracked:
            if tracked.status == "executing":
                tracked.status = "completed"
                tracked.result = self._synthetic_error(tracked.tool_call, reason)
        return await self.drain_remaining()

    def _process_queue(self) -> None:
        if self._discarded:
            return
        for tracked in self._tracked:
            if tracked.status != "queued":
                continue
            if not self._can_execute(tracked):
                break
            tracked.status = "executing"
            tracked.task = asyncio.create_task(self._run_tool(tracked))

    def _can_execute(self, tracked: _TrackedTool) -> bool:
        executing = [item for item in self._tracked if item.status == "executing"]
        if not executing:
            return True
        if not tracked.is_concurrency_safe:
            return False
        return all(item.is_concurrency_safe for item in executing)

    async def _run_tool(self, tracked: _TrackedTool) -> None:
        # @@@streaming-tool-task-exit
        # ql-05 cannot let middleware-level exceptions disappear into a dead
        # task. Every tool_use must resolve to a ToolMessage, and queue
        # progression must re-run immediately when a task exits.
        try:
            tracked.result = await self._loop._execute_single_tool(tracked.tool_call, self._tool_context)
            tracked.status = "completed"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            tracked.result = self._tool_error(tracked.tool_call, str(exc))
            tracked.status = "completed"
        finally:
            if self._should_abort_siblings(tracked):
                await self._abort_siblings(
                    excluding=tracked,
                    reason="sibling aborted after bash error",
                )
            if not self._discarded:
                self._process_queue()

    def _should_abort_siblings(self, tracked: _TrackedTool) -> bool:
        if tracked.result is None:
            return False
        name = tracked.tool_call.get("name") or tracked.tool_call.get("function", {}).get("name", "")
        return name.lower() == "bash" and "<tool_use_error>" in tracked.result.content

    async def _abort_siblings(self, *, excluding: _TrackedTool, reason: str) -> None:
        # @@@bash-sibling-abort
        # Claude Code only fan-outs this abort for bash failures. Keep it
        # local to the current executor iteration so the parent loop survives
        # and later turns can continue with explicit tool errors.
        self._discarded = True
        running: list[asyncio.Task[ToolMessage]] = []
        for tracked in self._tracked:
            if tracked is excluding or tracked.status in {"completed", "yielded"}:
                continue
            if tracked.status == "queued":
                tracked.status = "completed"
                tracked.result = self._tool_error(tracked.tool_call, reason)
                continue
            if tracked.status == "executing" and tracked.task is not None:
                tracked.task.cancel()
                running.append(tracked.task)
        if running:
            await asyncio.gather(*running, return_exceptions=True)
        for tracked in self._tracked:
            if tracked is excluding or tracked.status != "executing":
                continue
            tracked.status = "completed"
            tracked.result = self._tool_error(tracked.tool_call, reason)

    def _synthetic_error(self, tool_call: dict[str, Any], reason: str) -> ToolMessage:
        return self._tool_error(
            tool_call,
            f"streaming discarded: {reason}",
        )

    def _tool_error(self, tool_call: dict[str, Any], error_text: str) -> ToolMessage:
        name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
        call_id = tool_call.get("id", "")
        return ToolMessage(
            content=f"<tool_use_error>{error_text}</tool_use_error>",
            tool_call_id=call_id,
            name=name,
        )


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

from core.runtime.middleware import AgentMiddleware as _BaseMiddleware


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
