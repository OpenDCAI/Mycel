"""ToolSearchService - Discover available tools via search.

Registers a single INLINE tool (tool_search) that queries ToolRegistry
to find matching tools by name or description.
"""

from __future__ import annotations

import json
import logging

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry

logger = logging.getLogger(__name__)

TOOL_SEARCH_SCHEMA = {
    "name": "tool_search",
    "description": (
        "Search for available deferred tools by name or keyword. "
        "Use 'select:ToolA,ToolB' for exact deferred-tool lookup (returns full schema). "
        "Use keywords for fuzzy search (up to 5 results). "
        "Deferred tools are only usable after discovery via this tool."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query. Use 'select:ToolA,ToolB' for exact deferred-tool lookup, or keywords for fuzzy search.",
            },
        },
        "required": ["query"],
    },
}


class ToolSearchService:
    """Provides tool_search as an INLINE tool for discovering DEFERRED tools."""

    def __init__(self, registry: ToolRegistry):
        self._registry = registry
        registry.register(
            ToolEntry(
                name="tool_search",
                mode=ToolMode.INLINE,
                schema=TOOL_SEARCH_SCHEMA,
                handler=self._search,
                source="ToolSearchService",
                is_concurrency_safe=True,
                is_read_only=True,
            )
        )
        logger.info("ToolSearchService initialized")

    def _search(self, query: str = "", tool_context=None, **kwargs) -> str:
        select_names: list[str] = []
        normalized = query.strip()
        if normalized.lower().startswith("select:"):
            select_names = [name.strip() for name in normalized[len("select:"):].split(",") if name.strip()]

        results = self._registry.search(query, modes={ToolMode.DEFERRED})
        if select_names:
            found_names = {entry.name for entry in results}
            missing = [name for name in select_names if name not in found_names]
            inline = [name for name in missing if (entry := self._registry.get(name)) is not None and entry.mode == ToolMode.INLINE]
            unknown = [name for name in missing if self._registry.get(name) is None]
            if inline or unknown:
                parts: list[str] = []
                if inline:
                    parts.append(f"inline/already-available tools: {', '.join(inline)}")
                if unknown:
                    parts.append(f"unknown tools: {', '.join(unknown)}")
                raise ValueError(
                    "tool_search select: only supports deferred tools; "
                    + "; ".join(parts)
                )
        else:
            results = results[:5]
        if tool_context is not None and hasattr(tool_context, "discovered_tool_names"):
            tool_context.discovered_tool_names.update(entry.name for entry in results)
        schemas = [e.get_schema() for e in results]
        return json.dumps(schemas, indent=2, ensure_ascii=False)
