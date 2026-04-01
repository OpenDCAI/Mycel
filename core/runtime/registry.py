from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum

Handler = Callable[..., str] | Callable[..., Awaitable[str]]
SchemaProvider = dict | Callable[[], dict]


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

    def get_schema(self) -> dict:
        return self.schema() if callable(self.schema) else self.schema


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

    def get_inline_schemas(self) -> list[dict]:
        return [e.get_schema() for e in self._tools.values() if e.mode == ToolMode.INLINE]

    def search(self, query: str) -> list[ToolEntry]:
        """Return all matching tools (including inline) for tool_search."""
        q = query.lower()
        results = []
        for entry in self._tools.values():
            schema = entry.get_schema()
            name = schema.get("name", "")
            desc = schema.get("description", "")
            if q in name.lower() or q in desc.lower():
                results.append(entry)
        # If no match, return all
        if not results:
            results = list(self._tools.values())
        return results

    def list_all(self) -> list[ToolEntry]:
        return list(self._tools.values())
