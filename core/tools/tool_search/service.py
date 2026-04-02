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
        "Search for available tools by name or keyword. "
        "Use 'select:ToolA,ToolB' for exact lookup (returns full schema). "
        "Use keywords for fuzzy search (up to 5 results). "
        "Deferred tools are only usable after discovery via this tool."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query. Use 'select:ToolA,ToolB' for exact name lookup, or keywords for fuzzy search.",
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

    def _search(self, query: str = "", **kwargs) -> str:
        results = self._registry.search(query)
        schemas = [e.get_schema() for e in results]
        return json.dumps(schemas, indent=2, ensure_ascii=False)
