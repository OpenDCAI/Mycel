from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any, NotRequired, Required, TypedDict, Unpack

from core.runtime.tool_result import ToolResultEnvelope

type ToolSchema = dict[str, Any]
type ToolHandlerResult = str | ToolResultEnvelope
type ToolArgs = dict[str, Any]
type ToolPropertySchema = dict[str, Any]
type ToolProperties = dict[str, ToolPropertySchema]

type Handler = Callable[..., ToolHandlerResult] | Callable[..., Awaitable[ToolHandlerResult]]
type SchemaProvider = ToolSchema | Callable[[], ToolSchema]
type ConcurrencySafety = bool | Callable[[ToolArgs], bool]
type ToolInputValidator = Callable[[ToolArgs, Any], ToolArgs | None] | Callable[[ToolArgs, Any], Awaitable[ToolArgs | None]]


class _ToolEntryDefaults(TypedDict):
    search_hint: str
    is_concurrency_safe: ConcurrencySafety
    is_read_only: bool
    is_destructive: bool
    context_schema: ToolSchema | None
    validate_input: ToolInputValidator | None


class _ToolEntryBuildArgs(TypedDict, total=False):
    name: Required[str]
    mode: Required[ToolMode]
    schema: Required[SchemaProvider]
    handler: Required[Handler]
    source: Required[str]
    search_hint: NotRequired[str]
    is_concurrency_safe: NotRequired[ConcurrencySafety]
    is_read_only: NotRequired[bool]
    is_destructive: NotRequired[bool]
    context_schema: NotRequired[ToolSchema | None]
    validate_input: NotRequired[ToolInputValidator | None]


class ToolMode(Enum):
    INLINE = "inline"
    DEFERRED = "deferred"


@dataclass
class ToolEntry:
    name: str
    mode: ToolMode
    schema: SchemaProvider
    handler: Handler
    source: str
    search_hint: str = ""  # 3-10 word capability description for ToolSearch matching
    is_concurrency_safe: ConcurrencySafety = False  # fail-closed: assume not safe
    is_read_only: bool = False  # fail-closed: assume write operation
    is_destructive: bool = False  # advisory metadata for permission/UI layers
    context_schema: ToolSchema | None = None  # fields this tool needs from ToolUseContext
    validate_input: ToolInputValidator | None = None

    def get_schema(self) -> ToolSchema:
        return self.schema() if callable(self.schema) else self.schema


TOOL_DEFAULTS: _ToolEntryDefaults = {
    "search_hint": "",
    "is_concurrency_safe": False,
    "is_read_only": False,
    "is_destructive": False,
    "context_schema": None,
    "validate_input": None,
}


def build_tool(**kwargs: Unpack[_ToolEntryBuildArgs]) -> ToolEntry:
    """Factory that fills in safety defaults. Fail-closed: assumes write + non-concurrent."""
    merged: _ToolEntryBuildArgs = {**TOOL_DEFAULTS, **kwargs}
    return ToolEntry(**merged)


def make_tool_schema(
    *,
    name: str,
    description: str,
    properties: ToolProperties,
    required: list[str] | None = None,
    parameter_overrides: ToolSchema | None = None,
) -> ToolSchema:
    parameters: ToolSchema = {
        "type": "object",
        "properties": properties,
    }
    if required:
        parameters["required"] = required
    if parameter_overrides:
        parameters.update(parameter_overrides)
    return {
        "name": name,
        "description": description,
        "parameters": parameters,
    }


class ToolRegistry:
    """Central registry for all tools.

    Tools with INLINE mode are injected into every model call.
    Tools with DEFERRED mode are only discoverable via tool_search.
    """

    def __init__(
        self,
        allowed_tools: set[str] | None = None,
        blocked_tools: set[str] | None = None,
    ):
        self._tools: dict[str, ToolEntry] = {}
        self._allowed_tools = allowed_tools
        self._blocked_tools = blocked_tools or set()

    @property
    def blocked_tools(self) -> set[str]:
        return self._blocked_tools

    def register(self, entry: ToolEntry) -> None:
        if self._allowed_tools is not None and entry.name not in self._allowed_tools:
            return  # silently skip
        if entry.name in self._blocked_tools:
            return  # silently skip disabled tools
        self._tools[entry.name] = entry

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def get_inline_schemas(self, discovered_tool_names: set[str] | None = None) -> list[dict]:
        discovered_tool_names = discovered_tool_names or set()
        return [
            self._sanitize_schema_for_model(e.get_schema())
            for e in self._tools.values()
            if e.mode == ToolMode.INLINE or e.name in discovered_tool_names
        ]

    def _sanitize_schema_for_model(self, schema: dict) -> dict:
        # @@@tool-schema-sanitize - runtime-only schema metadata is useful for
        # validator/readiness, but provider tool schemas must stay within the
        # subset the live model API accepts.
        def _walk(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: _walk(child) for key, child in value.items() if not (isinstance(key, str) and key.startswith("x-leon-"))}
            if isinstance(value, list):
                return [_walk(item) for item in value]
            return value

        return _walk(deepcopy(schema))

    def search(self, query: str, *, modes: set[ToolMode] | None = None) -> list[ToolEntry]:
        """Return matching tools with ranked relevance.

        Supports ``select:Name1,Name2`` for exact selection.
        Otherwise ranks by: search_hint > name > description.
        """
        q = query.strip()
        entries = [entry for entry in self._tools.values() if modes is None or entry.mode in modes]

        # --- select:<names> exact lookup ---
        if q.lower().startswith("select:"):
            names = [n.strip() for n in q[len("select:") :].split(",") if n.strip()]
            results = [self._tools[n] for n in names if n in self._tools and (modes is None or self._tools[n].mode in modes)]
            return results

        # --- keyword search with ranking ---
        keywords = q.lower().split()
        if not keywords:
            return list(entries)

        scored: list[tuple[int, ToolEntry]] = []
        for entry in entries:
            schema = entry.get_schema()
            name_lower = entry.name.lower()
            hint_lower = entry.search_hint.lower()
            desc_lower = schema.get("description", "").lower()

            score = 0
            for kw in keywords:
                if kw in hint_lower:
                    score += 3
                if kw in name_lower:
                    score += 2
                if kw in desc_lower:
                    score += 1
            if score > 0:
                scored.append((score, entry))

        if not scored:
            return []

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored]

    def list_all(self) -> list[ToolEntry]:
        return list(self._tools.values())
