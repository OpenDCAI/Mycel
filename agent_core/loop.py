"""QueryLoop — the minimal core turn loop.

The bare agentic path: hydrate → (before_model middleware) → model call via the
middleware chain → parse tool calls → execute via the tool-call chain → append →
save → next turn → terminate. Everything else (streaming-tool overlap, the model
error-recovery state machine, memory-compaction notices, notification
follow-through, concurrency batching, deferred-tool discovery) lives in optional
layers — see ARCHITECTURE.md.

Depends only on ``langchain_core.messages`` + the agent_core foundation.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from agent_core.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from agent_core.ports.checkpoint import CheckpointStore, ThreadCheckpointState
from agent_core.registry import ToolRegistry
from agent_core.state import AppState, BootstrapConfig, ToolUseContext

logger = logging.getLogger(__name__)

DEFAULT_MAX_TURNS = 50


class TerminalReason(str, Enum):
    completed = "completed"
    max_turns = "max_turns"
    model_error = "model_error"
    aborted_tools = "aborted_tools"


@dataclass(frozen=True)
class TerminalState:
    reason: TerminalReason
    turn_count: int
    error: str | None = None


# -- middleware chain folding (verbatim mechanic from the original loop) --


def _make_model_wrapper(
    mw: AgentMiddleware,
    next_handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
) -> Callable[[ModelRequest], Awaitable[ModelResponse]]:
    async def wrapper(request: ModelRequest) -> ModelResponse:
        return await mw.awrap_model_call(request, next_handler)

    return wrapper


def _make_tool_wrapper(
    mw: AgentMiddleware,
    next_handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
) -> Callable[[ToolCallRequest], Awaitable[ToolMessage]]:
    async def wrapper(request: ToolCallRequest) -> ToolMessage:
        return await mw.awrap_tool_call(request, next_handler)

    return wrapper


def _mw_overrides_model_call(mw: AgentMiddleware) -> bool:
    mw_type = type(mw)
    return mw_type.__dict__.get("awrap_model_call") is not None or mw_type.__dict__.get("wrap_model_call") is not None


def _mw_overrides_tool_call(mw: AgentMiddleware) -> bool:
    mw_type = type(mw)
    return mw_type.__dict__.get("awrap_tool_call") is not None or mw_type.__dict__.get("wrap_tool_call") is not None


class QueryLoop:
    """A single agent's turn loop. One instance drives one logical agent."""

    def __init__(
        self,
        *,
        model: Any,
        registry: ToolRegistry,
        system_prompt: SystemMessage | str | None = None,
        middleware: list[AgentMiddleware] | None = None,
        checkpoint_store: CheckpointStore | None = None,
        app_state: AppState | None = None,
        bootstrap: BootstrapConfig | None = None,
        runtime: Any = None,
        max_turns: int = DEFAULT_MAX_TURNS,
        can_use_tool: Callable[..., Any] | None = None,
    ) -> None:
        self.model = model
        self._registry = registry
        if isinstance(system_prompt, str):
            system_prompt = SystemMessage(content=system_prompt)
        self.system_prompt = system_prompt
        self.middleware = list(middleware or [])
        self._checkpoint_store = checkpoint_store
        self._app_state = app_state
        self._bootstrap = bootstrap
        self._runtime = runtime
        self.max_turns = max_turns
        self._can_use_tool = can_use_tool
        self.last_terminal: TerminalState | None = None

    # -- public API --

    async def query(self, input: Any, config: dict | None = None):
        """Async generator yielding ``{"agent": ...}`` / ``{"tools": ...}`` events
        and a final ``{"terminal": TerminalState, "transition": None}``."""
        config = config or {}
        thread_id = config.get("configurable", {}).get("thread_id", "default")

        messages = await self._hydrate(thread_id)
        messages.extend(self._parse_input(input))
        self._sync_app_state(messages=messages, turn_count=0)

        terminal: TerminalState | None = None
        turn = 0
        try:
            while turn < self.max_turns:
                turn += 1
                tool_context = self._build_tool_use_context(messages, thread_id)
                messages_for_query, injected = await self._apply_before_model(messages, config)
                if injected:
                    messages.extend(injected)

                try:
                    response = await self._invoke_model(messages_for_query, config)
                except Exception as exc:  # noqa: BLE001 - terminal model failure
                    logger.exception("model call failed")
                    terminal = TerminalState(TerminalReason.model_error, turn, str(exc))
                    break

                ai_msg = next((m for m in response.result if isinstance(m, AIMessage)), None)
                if ai_msg is None:
                    terminal = TerminalState(TerminalReason.model_error, turn, "model returned no AIMessage")
                    break

                self._sync_app_state(messages=messages, turn_count=turn)
                tool_calls = self._extract_tool_calls(ai_msg)

                yield {"agent": {"messages": [ai_msg]}}

                if not tool_calls:
                    if self._ai_has_visible_content(ai_msg):
                        messages.append(ai_msg)
                    terminal = TerminalState(TerminalReason.completed, turn)
                    break

                try:
                    tool_results = await self._execute_tools(tool_calls, tool_context)
                except asyncio.CancelledError:
                    terminal = TerminalState(TerminalReason.aborted_tools, turn, "tool execution cancelled")
                    raise
                yield {"tools": {"messages": tool_results}}

                messages.append(ai_msg)
                messages.extend(tool_results)
                self._sync_app_state(messages=messages, turn_count=turn)
        finally:
            await self._save(thread_id, messages)

        if terminal is None:
            terminal = TerminalState(TerminalReason.max_turns, turn)
        self._sync_app_state(messages=messages, turn_count=turn)
        self.last_terminal = terminal
        yield {"terminal": terminal, "transition": None}

    async def astream(self, input: Any, config: dict | None = None):
        """Yield agent/tools events; raise on a non-``completed`` terminal."""
        async for event in self.query(input, config):
            if "terminal" in event:
                terminal: TerminalState = event["terminal"]
                if terminal.reason != TerminalReason.completed:
                    raise RuntimeError(terminal.error or f"agent terminated: {terminal.reason.value}")
                return
            yield event

    async def ainvoke(self, input: Any, config: dict | None = None) -> dict:
        """Drain the loop, returning all messages produced + the terminal reason."""
        collected: list[BaseMessage] = []
        terminal: TerminalState | None = None
        async for event in self.query(input, config):
            if "agent" in event:
                collected.extend(event["agent"]["messages"])
            elif "tools" in event:
                collected.extend(event["tools"]["messages"])
            elif "terminal" in event:
                terminal = event["terminal"]
        return {
            "messages": collected,
            "reason": terminal.reason.value if terminal else None,
            "terminal": terminal,
        }

    # -- model call --

    async def _invoke_model(self, messages: list, config: dict) -> ModelResponse:
        async def innermost(request: ModelRequest) -> ModelResponse:
            bound = self._bind_model(request.model, request.tools or [])
            call_messages: list = []
            if request.system_message:
                call_messages.append(request.system_message)
            call_messages.extend(request.messages)
            result = await bound.ainvoke(call_messages)
            if not isinstance(result, list):
                result = [result]
            return ModelResponse(result=result, request_messages=list(request.messages))

        request = ModelRequest(
            model=self.model,
            messages=messages,
            system_message=self.system_prompt,
            tools=self._registry.get_inline_schemas(),
        )
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]] = innermost
        for mw in reversed(self.middleware):
            if _mw_overrides_model_call(mw):
                handler = _make_model_wrapper(mw, handler)
        return await handler(request)

    def _bind_model(self, model: Any, tools: list) -> Any:
        if not tools:
            return model
        binder = getattr(model, "bind_tools", None)
        if not callable(binder):
            return model
        try:
            return binder(tools)
        except Exception:  # noqa: BLE001 - bind is best-effort; fall back to raw model
            logger.debug("bind_tools failed; using unbound model", exc_info=True)
            return model

    # -- tool execution --

    async def _execute_tools(self, tool_calls: list[dict], tool_context: Any) -> list[ToolMessage]:
        results: list[ToolMessage] = []
        for tool_call in tool_calls:
            results.append(await self._execute_single_tool(tool_call, tool_context))
        return results

    async def _execute_single_tool(self, tool_call: dict, tool_context: Any) -> ToolMessage:
        name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
        call_id = tool_call.get("id", "") or ""
        args = tool_call.get("args")
        if args is None:
            args = tool_call.get("function", {}).get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:  # noqa: BLE001
                args = {}

        normalized = {"name": name, "args": args, "id": call_id}
        request = ToolCallRequest(tool_call=normalized, tool=None, state=tool_context, runtime=self._runtime)

        async def innermost(req: ToolCallRequest) -> ToolMessage:
            tc = req.tool_call
            t_name, t_id, t_args = tc.get("name", ""), tc.get("id", ""), tc.get("args", {})
            entry = self._registry.get(t_name)
            if entry is None:
                return ToolMessage(
                    content=f"<tool_use_error>Tool '{t_name}' not found</tool_use_error>",
                    tool_call_id=t_id,
                    name=t_name,
                )
            try:
                if asyncio.iscoroutinefunction(entry.handler):
                    result = await entry.handler(**t_args)
                else:
                    result = await asyncio.to_thread(entry.handler, **t_args)
                if asyncio.iscoroutine(result):
                    result = await result
                return ToolMessage(content=str(result), tool_call_id=t_id, name=t_name)
            except Exception as exc:  # noqa: BLE001 - surface tool failure to the model
                return ToolMessage(
                    content=f"<tool_use_error>{exc}</tool_use_error>",
                    tool_call_id=t_id,
                    name=t_name,
                )

        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]] = innermost
        for mw in reversed(self.middleware):
            if _mw_overrides_tool_call(mw):
                handler = _make_tool_wrapper(mw, handler)
        return await handler(request)

    # -- before-model middleware (linear inject chain) --

    async def _apply_before_model(self, messages: list, config: dict) -> tuple[list, list]:
        current = list(messages)
        injected: list = []
        state = {"messages": current}
        for mw in self.middleware:
            abefore = getattr(mw, "abefore_model", None)
            before = getattr(mw, "before_model", None)
            update: Any = None
            if callable(abefore):
                maybe = abefore(state=state, runtime=self._runtime, config=config)
                if inspect.isawaitable(maybe):
                    maybe = await maybe
                update = maybe if isinstance(maybe, dict) else None
            elif callable(before):
                maybe = before(state=state, runtime=self._runtime, config=config)
                update = maybe if isinstance(maybe, dict) else None
            if not update:
                continue
            new_messages = update.get("messages")
            if not new_messages:
                continue
            if not isinstance(new_messages, list):
                new_messages = [new_messages]
            current.extend(new_messages)
            injected.extend(new_messages)
            state["messages"] = current
        return current, injected

    # -- context + state --

    def _build_tool_use_context(self, messages: list, thread_id: str) -> ToolUseContext:
        return ToolUseContext(
            bootstrap=self._effective_bootstrap(),
            get_app_state=self._get_app_state,
            set_app_state=self._set_app_state,
            can_use_tool=self._can_use_tool,
            messages=messages,
            thread_id=thread_id,
        )

    def _effective_bootstrap(self) -> BootstrapConfig:
        if self._bootstrap is None:
            self._bootstrap = BootstrapConfig(
                workspace_root=Path.cwd(),
                model_name=getattr(self.model, "model_name", None) or "agent",
            )
        return self._bootstrap

    def _get_app_state(self) -> AppState:
        if self._app_state is None:
            self._app_state = AppState()
        return self._app_state

    def _set_app_state(self, updater: Callable[[AppState], AppState]) -> AppState | None:
        if self._app_state is None:
            return None
        return self._app_state.set_state(updater)

    def _sync_app_state(self, *, messages: list | None = None, turn_count: int | None = None) -> None:
        if self._app_state is None:
            return

        def _upd(s: AppState) -> AppState:
            if messages is not None:
                s.messages = list(messages)
            if turn_count is not None:
                s.turn_count = turn_count
            return s

        self._app_state.set_state(_upd)

    # -- checkpoint hydrate / save --

    async def _hydrate(self, thread_id: str) -> list:
        if self._checkpoint_store is None:
            return []
        state = await self._checkpoint_store.load(thread_id)
        return list(state.messages) if state is not None else []

    async def _save(self, thread_id: str, messages: list) -> None:
        if self._checkpoint_store is None:
            return
        permission_ctx: dict = {}
        if self._app_state is not None:
            permission_ctx = self._app_state.tool_permission_context.model_dump()
        await self._checkpoint_store.save(
            thread_id,
            ThreadCheckpointState(
                messages=list(messages),
                tool_permission_context=permission_ctx,
                pending_permission_requests={},
                resolved_permission_requests={},
                memory_compaction_state={},
                integration_instruction_state={},
            ),
        )

    # -- helpers --

    @staticmethod
    def _extract_tool_calls(ai_msg: AIMessage) -> list[dict]:
        tool_calls = getattr(ai_msg, "tool_calls", None) or []
        if not tool_calls:
            tool_calls = ai_msg.additional_kwargs.get("tool_calls", []) or []
        return list(tool_calls)

    @staticmethod
    def _ai_has_visible_content(ai_msg: AIMessage) -> bool:
        content = getattr(ai_msg, "content", None)
        if isinstance(content, str):
            return bool(content.strip())
        if isinstance(content, list):
            return len(content) > 0
        return bool(content)

    def _parse_input(self, input: Any) -> list[BaseMessage]:
        if input is None:
            return []
        if isinstance(input, BaseMessage):
            return [input]
        if isinstance(input, str):
            return [HumanMessage(content=input)]
        if isinstance(input, dict) and "messages" in input:
            return self._coerce_messages(input["messages"])
        if isinstance(input, list):
            return self._coerce_messages(input)
        return []

    @staticmethod
    def _coerce_messages(raw: list) -> list[BaseMessage]:
        out: list[BaseMessage] = []
        for m in raw:
            if isinstance(m, BaseMessage):
                out.append(m)
                continue
            if isinstance(m, dict):
                role = m.get("role", "user")
                content = m.get("content", "")
                if role in ("assistant", "ai"):
                    out.append(AIMessage(content=content))
                elif role == "system":
                    out.append(SystemMessage(content=content))
                else:
                    out.append(HumanMessage(content=content))
        return out
