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
    search_hint: str = ""  # 3-10 word capability description for ToolSearch matching
    is_concurrency_safe: bool = False  # fail-closed: assume not safe
    is_read_only: bool = False  # fail-closed: assume write operation
    context_schema: dict | None = None  # fields this tool needs from ToolUseContext

    def get_schema(self) -> dict:
        return self.schema() if callable(self.schema) else self.schema


TOOL_DEFAULTS: dict[str, object] = {
    "is_concurrency_safe": False,
    "is_read_only": False,
    "context_schema": None,
}


def build_tool(**kwargs: object) -> ToolEntry:
    """Factory that fills in safety defaults. Fail-closed: assumes write + non-concurrent."""
    merged = {**TOOL_DEFAULTS, **kwargs}
    return ToolEntry(**merged)  # type: ignore[arg-type]


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
        """Return matching tools with ranked relevance.

        Supports ``select:Name1,Name2`` for exact selection.
        Otherwise ranks by: search_hint > name > description.
        """
        q = query.strip()

        # --- select:<names> exact lookup ---
        if q.lower().startswith("select:"):
            names = [n.strip() for n in q[len("select:"):].split(",") if n.strip()]
            results = [self._tools[n] for n in names if n in self._tools]
            return results

        # --- keyword search with ranking ---
        keywords = q.lower().split()
        if not keywords:
            return list(self._tools.values())

        scored: list[tuple[int, ToolEntry]] = []
        for entry in self._tools.values():
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
            return list(self._tools.values())

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored]

    def list_all(self) -> list[ToolEntry]:
        return list(self._tools.values())
