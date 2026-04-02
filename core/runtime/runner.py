from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.runtime.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import ToolMessage

from .errors import InputValidationError
from .permissions import ToolPermissionContext
from .registry import ToolRegistry
from .tool_result import (
    ToolResultEnvelope,
    materialize_tool_message,
    tool_error,
    tool_permission_denied,
    tool_success,
)
from .validator import ToolValidator

logger = logging.getLogger(__name__)


class _ToolSpecificValidationError(Exception):
    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


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

    @staticmethod
    def _get_request_hook(request: ToolCallRequest, hook_name: str):
        state = getattr(request, "state", None)
        if state is None:
            return None
        if isinstance(state, dict):
            hook = state.get(hook_name)
        else:
            hook = vars(state).get(hook_name)
        if hook is None:
            return None
        if isinstance(hook, list):
            return hook
        return hook if callable(hook) else None

    @staticmethod
    def _apply_result_hooks_sync(
        hook_or_hooks,
        payload: ToolMessage | ToolResultEnvelope,
        request: ToolCallRequest,
    ) -> ToolMessage | ToolResultEnvelope:
        if hook_or_hooks is None:
            return payload
        hooks = hook_or_hooks if isinstance(hook_or_hooks, list) else [hook_or_hooks]
        current = payload
        for hook in hooks:
            updated = hook(current, request)
            if updated is not None:
                current = updated
        return current

    @staticmethod
    async def _apply_result_hooks(
        hook_or_hooks,
        payload: ToolMessage | ToolResultEnvelope,
        request: ToolCallRequest,
    ) -> ToolMessage | ToolResultEnvelope:
        if hook_or_hooks is None:
            return payload
        hooks = hook_or_hooks if isinstance(hook_or_hooks, list) else [hook_or_hooks]
        current = payload
        for hook in hooks:
            updated = hook(current, request)
            if asyncio.iscoroutine(updated):
                updated = await updated
            if updated is not None:
                current = updated
        return current

    def _normalize_result(self, result: Any) -> ToolResultEnvelope:
        if isinstance(result, ToolResultEnvelope):
            return result
        return tool_success(result)

    @staticmethod
    def _inject_handler_context(entry, args: dict, request: ToolCallRequest) -> dict:
        state = getattr(request, "state", None)
        if state is None or "tool_context" in args:
            return args
        try:
            signature = inspect.signature(entry.handler)
        except (TypeError, ValueError):
            return args
        if "tool_context" not in signature.parameters:
            return args
        # @@@sa-04-tool-context-injection
        # The sub-agent boundary only becomes real once the live ToolUseContext
        # can cross the tool runner into handlers that explicitly opt in.
        return {**args, "tool_context": state}

    @staticmethod
    def _coerce_permission_response(result) -> tuple[str | None, str | None]:
        if result is None:
            return None, None
        if isinstance(result, str):
            return result, None
        if isinstance(result, dict):
            decision = result.get("decision") or result.get("permission")
            message = result.get("message")
            return decision, message
        decision = getattr(result, "decision", None) or getattr(result, "permission", None)
        message = getattr(result, "message", None)
        return decision, message

    @staticmethod
    def _permission_denied_result(decision: str, message: str | None) -> ToolResultEnvelope:
        if decision == "ask":
            text = message or "Permission required"
        else:
            text = message or "Permission denied"
        return tool_permission_denied(
            text,
            metadata={"decision": decision, "error_type": "permission_resolution"},
        )

    def _run_tool_specific_validation_sync(self, entry, args: dict, request: ToolCallRequest) -> dict:
        validator = getattr(entry, "validate_input", None)
        if validator is None:
            return args
        result = validator(dict(args), request)
        if result is None:
            return args
        if isinstance(result, dict):
            if result.get("result") is False or result.get("ok") is False:
                raise _ToolSpecificValidationError(
                    result.get("message") or "Tool-specific validation failed",
                    result.get("errorCode") or result.get("error_code"),
                )
            return result
        raise InputValidationError(str(result))

    async def _run_tool_specific_validation_async(self, entry, args: dict, request: ToolCallRequest) -> dict:
        validator = getattr(entry, "validate_input", None)
        if validator is None:
            return args
        result = validator(dict(args), request)
        if asyncio.iscoroutine(result):
            result = await result
        if result is None:
            return args
        if isinstance(result, dict):
            if result.get("result") is False or result.get("ok") is False:
                raise _ToolSpecificValidationError(
                    result.get("message") or "Tool-specific validation failed",
                    result.get("errorCode") or result.get("error_code"),
                )
            return result
        raise InputValidationError(str(result))

    def _run_pre_tool_use_sync(self, request: ToolCallRequest, *, name: str, args: dict, entry) -> tuple[dict, str | None, str | None]:
        hooks = self._get_request_hook(request, "pre_tool_use")
        if hooks is None:
            return args, None, None
        payload = {"name": name, "args": dict(args), "entry": entry}
        permission: str | None = None
        message: str | None = None
        hook_list = hooks if isinstance(hooks, list) else [hooks]
        for hook in hook_list:
            updated = hook(payload, request)
            if updated is None:
                continue
            if isinstance(updated, dict):
                if "args" in updated:
                    payload["args"] = updated["args"]
                if "name" in updated:
                    payload["name"] = updated["name"]
                if "entry" in updated:
                    payload["entry"] = updated["entry"]
                new_permission, new_message = self._coerce_permission_response(updated)
                if new_permission is not None:
                    permission = new_permission
                    message = new_message
        return payload["args"], permission, message

    async def _run_pre_tool_use_async(self, request: ToolCallRequest, *, name: str, args: dict, entry) -> tuple[dict, str | None, str | None]:
        hooks = self._get_request_hook(request, "pre_tool_use")
        if hooks is None:
            return args, None, None
        payload = {"name": name, "args": dict(args), "entry": entry}
        permission: str | None = None
        message: str | None = None
        hook_list = hooks if isinstance(hooks, list) else [hooks]
        for hook in hook_list:
            updated = hook(payload, request)
            if asyncio.iscoroutine(updated):
                updated = await updated
            if updated is None:
                continue
            if isinstance(updated, dict):
                if "args" in updated:
                    payload["args"] = updated["args"]
                if "name" in updated:
                    payload["name"] = updated["name"]
                if "entry" in updated:
                    payload["entry"] = updated["entry"]
                new_permission, new_message = self._coerce_permission_response(updated)
                if new_permission is not None:
                    permission = new_permission
                    message = new_message
        return payload["args"], permission, message

    def _resolve_permission(self, request: ToolCallRequest, *, name: str, args: dict, entry, hook_permission: str | None, hook_message: str | None) -> ToolResultEnvelope | None:
        if hook_permission == "deny":
            return self._permission_denied_result("deny", hook_message)

        state = getattr(request, "state", None)
        checker = None
        if state is not None:
            checker = state.get("can_use_tool") if isinstance(state, dict) else getattr(state, "can_use_tool", None)
        rule_permission: str | None = None
        rule_message: str | None = None
        permission_context = ToolPermissionContext(
            is_read_only=bool(getattr(entry, "is_read_only", False)),
            is_destructive=bool(getattr(entry, "is_destructive", False)),
        )
        if callable(checker):
            rule_permission, rule_message = self._coerce_permission_response(
                checker(name, args, permission_context, request)
            )

        if hook_permission == "allow":
            if rule_permission in {"deny", "ask"}:
                return self._permission_denied_result(rule_permission, rule_message)
            return None

        if rule_permission in {"deny", "ask"}:
            return self._permission_denied_result(rule_permission, rule_message)
        return None

    def _materialize_result(
        self,
        envelope: ToolResultEnvelope,
        *,
        name: str,
        call_id: str,
        source: str,
    ) -> ToolMessage:
        return materialize_tool_message(
            envelope,
            tool_call_id=call_id,
            name=name,
            source=source,
        )

    @staticmethod
    def _entry_source(entry) -> str:
        return "mcp" if getattr(entry, "source", None) == "mcp" else "local"

    def _finalize_registered_result(
        self,
        envelope: ToolResultEnvelope,
        *,
        name: str,
        call_id: str,
        source: str,
    ) -> ToolMessage | ToolResultEnvelope:
        if source == "mcp":
            return envelope
        return self._materialize_result(
            envelope,
            name=name,
            call_id=call_id,
            source=source,
        )

    @staticmethod
    def _select_hook_name(kind: str) -> str:
        if kind == "error":
            return "post_tool_use_failure"
        if kind == "permission_denied":
            return "permission_denied_hooks"
        return "post_tool_use"

    def _validate_and_run(self, request: ToolCallRequest, name: str, args: dict, call_id: str) -> ToolMessage | ToolResultEnvelope | None:
        entry = self._registry.get(name)
        if entry is None:
            return None  # not our tool
        source = self._entry_source(entry)

        schema = entry.get_schema()
        try:
            self._validator.validate(schema, args)
        except InputValidationError as e:
            return self._finalize_registered_result(
                tool_error(
                    f"InputValidationError: {name} failed due to the following issue:\n{e}",
                    metadata={"error_type": "input_validation"},
                ),
                name=name,
                call_id=call_id,
                source=source,
            )
        try:
            args = self._run_tool_specific_validation_sync(entry, args, request)
        except _ToolSpecificValidationError as e:
            return self._finalize_registered_result(
                tool_error(
                    f"ToolValidationError: {name} failed due to the following issue:\n{e}",
                    metadata={"error_type": "tool_input_validation", "error_code": e.error_code},
                ),
                name=name,
                call_id=call_id,
                source=source,
            )
        except InputValidationError as e:
            return self._finalize_registered_result(
                tool_error(
                    f"ToolValidationError: {name} failed due to the following issue:\n{e}",
                    metadata={"error_type": "tool_input_validation"},
                ),
                name=name,
                call_id=call_id,
                source=source,
            )
        args, hook_permission, hook_message = self._run_pre_tool_use_sync(
            request,
            name=name,
            args=args,
            entry=entry,
        )
        permission_result = self._resolve_permission(
            request,
            name=name,
            args=args,
            entry=entry,
            hook_permission=hook_permission,
            hook_message=hook_message,
        )
        if permission_result is not None:
            return self._finalize_registered_result(
                permission_result,
                name=name,
                call_id=call_id,
                source=source,
            )

        args = self._inject_handler_context(entry, args, request)
        try:
            result = entry.handler(**args)
            if asyncio.iscoroutine(result):
                result = asyncio.get_event_loop().run_until_complete(result)
            return self._finalize_registered_result(
                self._normalize_result(result),
                name=name,
                call_id=call_id,
                source=source,
            )
        except Exception as e:
            logger.exception("Tool %s execution failed", name)
            return self._finalize_registered_result(
                tool_error(
                    f"<tool_use_error>{e}</tool_use_error>",
                    metadata={"error_type": "tool_execution"},
                ),
                name=name,
                call_id=call_id,
                source=source,
            )

    async def _validate_and_run_async(self, request: ToolCallRequest, name: str, args: dict, call_id: str) -> ToolMessage | ToolResultEnvelope | None:
        entry = self._registry.get(name)
        if entry is None:
            return None
        source = self._entry_source(entry)

        schema = entry.get_schema()
        try:
            self._validator.validate(schema, args)
        except InputValidationError as e:
            return self._finalize_registered_result(
                tool_error(
                    f"InputValidationError: {name} failed due to the following issue:\n{e}",
                    metadata={"error_type": "input_validation"},
                ),
                name=name,
                call_id=call_id,
                source=source,
            )
        try:
            args = await self._run_tool_specific_validation_async(entry, args, request)
        except _ToolSpecificValidationError as e:
            return self._finalize_registered_result(
                tool_error(
                    f"ToolValidationError: {name} failed due to the following issue:\n{e}",
                    metadata={"error_type": "tool_input_validation", "error_code": e.error_code},
                ),
                name=name,
                call_id=call_id,
                source=source,
            )
        except InputValidationError as e:
            return self._finalize_registered_result(
                tool_error(
                    f"ToolValidationError: {name} failed due to the following issue:\n{e}",
                    metadata={"error_type": "tool_input_validation"},
                ),
                name=name,
                call_id=call_id,
                source=source,
            )

        args, hook_permission, hook_message = await self._run_pre_tool_use_async(
            request,
            name=name,
            args=args,
            entry=entry,
        )
        permission_result = self._resolve_permission(
            request,
            name=name,
            args=args,
            entry=entry,
            hook_permission=hook_permission,
            hook_message=hook_message,
        )
        if permission_result is not None:
            return self._finalize_registered_result(
                permission_result,
                name=name,
                call_id=call_id,
                source=source,
            )

        args = self._inject_handler_context(entry, args, request)
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
            return self._finalize_registered_result(
                self._normalize_result(result),
                name=name,
                call_id=call_id,
                source=source,
            )
        except Exception as e:
            logger.exception("Tool %s execution failed", name)
            return self._finalize_registered_result(
                tool_error(
                    f"<tool_use_error>{e}</tool_use_error>",
                    metadata={"error_type": "tool_execution"},
                ),
                name=name,
                call_id=call_id,
                source=source,
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
        entry = self._registry.get(name)
        result = self._validate_and_run(request, name, args, call_id)
        if result is not None:
            source = self._entry_source(entry) if entry is not None else "local"
            if isinstance(result, ToolResultEnvelope):
                hook_name = self._select_hook_name(result.kind)
                hooks = self._get_request_hook(request, hook_name)
                hooked = self._apply_result_hooks_sync(hooks, result, request) if hooks else result
                if isinstance(hooked, ToolMessage):
                    return hooked
                return self._materialize_result(hooked, name=name, call_id=call_id, source=source)
            kind = result.additional_kwargs.get("tool_result_meta", {}).get("kind")
            hook_name = self._select_hook_name(kind)
            hooks = self._get_request_hook(request, hook_name)
            maybe_updated = self._apply_result_hooks_sync(hooks, result, request) if hooks else result
            if isinstance(maybe_updated, ToolMessage):
                return maybe_updated
            return self._materialize_result(maybe_updated, name=name, call_id=call_id, source=source)
        upstream = handler(request)
        return upstream

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> ToolMessage:
        name, args, call_id = self._extract_call_info(request)
        entry = self._registry.get(name)
        source = self._entry_source(entry) if entry is not None else "local"
        result = await self._validate_and_run_async(request, name, args, call_id)
        if result is not None:
            # @@@tool-result-ordering
            # te-02 keeps local tools materialize-first, but registered MCP
            # tools must stay envelope-first so post hooks can see and modify
            # structured output before final ToolMessage creation.
            if isinstance(result, ToolResultEnvelope):
                hook_name = self._select_hook_name(result.kind)
                hooks = self._get_request_hook(request, hook_name)
                hooked = await self._apply_result_hooks(hooks, result, request)
                if isinstance(hooked, ToolMessage):
                    return hooked
                return self._materialize_result(hooked, name=name, call_id=call_id, source=source)
            meta = result.additional_kwargs.get("tool_result_meta", {})
            hook_name = self._select_hook_name(meta.get("kind"))
            hooks = self._get_request_hook(request, hook_name)
            hooked = await self._apply_result_hooks(hooks, result, request)
            if isinstance(hooked, ToolMessage):
                return hooked
            return self._materialize_result(hooked, name=name, call_id=call_id, source=source)

        upstream = await handler(request)
        post_tool_use = self._get_request_hook(request, "post_tool_use")
        if isinstance(upstream, ToolResultEnvelope):
            # MCP/upstream path: post hooks get first shot at the structured
            # result, and only then do we materialize the ToolMessage.
            hooked = await self._apply_result_hooks(post_tool_use, upstream, request)
            if isinstance(hooked, ToolMessage):
                return hooked
            return self._materialize_result(hooked, name=name, call_id=call_id, source="mcp")
        if isinstance(upstream, ToolMessage):
            hooked = await self._apply_result_hooks(post_tool_use, upstream, request)
            return hooked if isinstance(hooked, ToolMessage) else self._materialize_result(hooked, name=name, call_id=call_id, source="mcp")
        return upstream
