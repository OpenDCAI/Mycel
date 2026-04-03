"""Web Service - registers WebSearch and WebFetch tools with ToolRegistry.

Tools:
- WebSearch: Web search (Tavily -> Exa -> Firecrawl fallback)
- WebFetch: Fetch web content and extract information using AI
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from core.tools.web.fetchers.jina import JinaFetcher
from core.tools.web.fetchers.markdownify import MarkdownifyFetcher
from core.tools.web.searchers.exa import ExaSearcher
from core.tools.web.searchers.firecrawl import FirecrawlSearcher
from core.tools.web.searchers.tavily import TavilySearcher
from core.tools.web.types import FetchLimits, FetchResult, SearchResult


class WebService:
    """Registers WebSearch and WebFetch tools into ToolRegistry."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        tavily_api_key: str | None = None,
        exa_api_key: str | None = None,
        firecrawl_api_key: str | None = None,
        jina_api_key: str | None = None,
        fetch_limits: FetchLimits | None = None,
        max_search_results: int = 5,
        timeout: int = 15,
        extraction_model: Any = None,
    ):
        self.fetch_limits = fetch_limits or FetchLimits()
        self.max_search_results = max_search_results
        self.timeout = timeout
        self._extraction_model = extraction_model

        self._searchers: list[tuple[str, Any]] = []
        if tavily_api_key:
            self._searchers.append(("Tavily", TavilySearcher(tavily_api_key, max_search_results, timeout)))
        if exa_api_key:
            self._searchers.append(("Exa", ExaSearcher(exa_api_key, max_search_results, timeout)))
        if firecrawl_api_key:
            self._searchers.append(("Firecrawl", FirecrawlSearcher(firecrawl_api_key, max_search_results, timeout)))

        self._fetchers: list[tuple[str, Any]] = []
        if jina_api_key:
            self._fetchers.append(("Jina", JinaFetcher(jina_api_key, self.fetch_limits, timeout)))
        self._fetchers.append(("Markdownify", MarkdownifyFetcher(self.fetch_limits, timeout)))

        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        registry.register(
            ToolEntry(
                name="WebSearch",
                mode=ToolMode.DEFERRED,
                schema={
                    "name": "WebSearch",
                    "description": (
                        "Search the web. Returns titles, URLs, and text snippets. "
                        "Use for current events, documentation lookups, or fact-checking. Max 10 results per query."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results (default: 5)",
                            },
                            "include_domains": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Only include results from these domains",
                            },
                            "exclude_domains": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Exclude results from these domains",
                            },
                        },
                        "required": ["query"],
                    },
                },
                handler=self._web_search,
                source="WebService",
                is_concurrency_safe=True,
                is_read_only=True,
            )
        )

        registry.register(
            ToolEntry(
                name="WebFetch",
                mode=ToolMode.DEFERRED,
                schema={
                    "name": "WebFetch",
                    "description": (
                        "Fetch a URL and extract specific information via AI. Returns processed text, not raw HTML. "
                        "Provide a focused prompt describing what to extract. "
                        "Useful for reading documentation pages, API references, or articles."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to fetch content from",
                            },
                            "prompt": {
                                "type": "string",
                                "description": "What information to extract from the page",
                            },
                        },
                        "required": ["url", "prompt"],
                    },
                },
                handler=self._web_fetch,
                source="WebService",
                is_concurrency_safe=True,
                is_read_only=True,
            )
        )

    async def _web_search(
        self,
        query: str,
        max_results: int | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> str:
        if not self._searchers:
            return "No search providers configured"

        effective_max = max_results or self.max_search_results

        for name, searcher in self._searchers:
            try:
                result: SearchResult = await searcher.search(
                    query=query,
                    max_results=effective_max,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                )
                if not result.error:
                    return result.format_output()
            except Exception:
                continue

        return "All search providers failed"

    async def _web_fetch(self, url: str, prompt: str) -> str:
        if not self._fetchers:
            return "Error: No fetch providers configured"

        fetch_result: FetchResult | None = None
        for name, fetcher in self._fetchers:
            try:
                result = await fetcher.fetch(url)
                if not result.error:
                    fetch_result = result
                    break
            except Exception:
                continue

        if fetch_result is None:
            return f"Error: Failed to fetch URL: {url}"

        content = fetch_result.content or ""
        if not content:
            return f"Error: No content retrieved from URL: {url}"

        max_chars = 100_000
        if len(content) > max_chars:
            content = content[:max_chars]

        return await self._ai_extract(content, prompt, url)

    async def _ai_extract(self, content: str, prompt: str, url: str) -> str:
        try:
            model = self._extraction_model
            if model is None:
                preview = content[:5000] if len(content) > 5000 else content
                return f"AI extraction unavailable. Configure an extraction model. Raw content:\n\n{preview}"

            extraction_prompt = (
                f"You are extracting information from a web page.\n"
                f"URL: {url}\n\n"
                f"Web page content:\n{content}\n\n"
                f"User's request: {prompt}\n\n"
                f"Provide a concise, relevant answer based on the web page content."
            )

            response = await asyncio.wait_for(
                model.ainvoke(extraction_prompt, config={"callbacks": []}),
                timeout=30,
            )
            return response.content
        except TimeoutError:
            preview = content[:5000] if len(content) > 5000 else content
            return f"AI extraction timed out (30s). Raw content preview:\n\n{preview}"
        except Exception as e:
            preview = content[:5000] if len(content) > 5000 else content
            return f"AI extraction failed ({e}). Raw content preview:\n\n{preview}"
