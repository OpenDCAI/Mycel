"""
Web Middleware - Web search and content fetching

Tools (pure Middleware implementation):
- web_search: Web search (Tavily → Exa → Firecrawl fallback)
- Fetch: Fetch web content and extract information using AI

Features:
- AI-powered content extraction (no chunking needed)
- Multi-provider fallback strategy
- PascalCase parameter naming
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import ToolMessage

from core.tools.web.fetchers.jina import JinaFetcher
from core.tools.web.fetchers.markdownify import MarkdownifyFetcher
from core.tools.web.searchers.exa import ExaSearcher
from core.tools.web.searchers.firecrawl import FirecrawlSearcher
from core.tools.web.searchers.tavily import TavilySearcher
from core.tools.web.types import FetchLimits, FetchResult, SearchResult


class WebMiddleware(AgentMiddleware):
    """
    Web Middleware - 纯 Middleware 实现 Web 搜索和内容获取

    特点：
    - 所有工具都在 middleware 层实现
    - AI-powered content extraction（无需分块）
    - 多提供商降级策略
    """

    TOOL_WEB_SEARCH = "web_search"
    TOOL_FETCH = "Fetch"

    def __init__(
        self,
        *,
        tavily_api_key: str | None = None,
        exa_api_key: str | None = None,
        firecrawl_api_key: str | None = None,
        jina_api_key: str | None = None,
        fetch_limits: FetchLimits | None = None,
        max_search_results: int = 5,
        timeout: int = 15,
        enabled_tools: dict[str, bool] | None = None,
        extraction_model: Any = None,
        verbose: bool = True,
    ):
        """
        初始化 Web middleware

        Args:
            tavily_api_key: Tavily API key（搜索主力）
            exa_api_key: Exa API key（搜索备选）
            firecrawl_api_key: Firecrawl API key（搜索兜底）
            jina_api_key: Jina API key（Fetch 主力）
            fetch_limits: Fetch 限制配置
            max_search_results: 最大搜索结果数
            timeout: 请求超时时间
            extraction_model: ChatModel for AI extraction (e.g. leon:mini resolved instance)
            verbose: 是否输出详细日志
        """
        self.fetch_limits = fetch_limits or FetchLimits()
        self.max_search_results = max_search_results
        self.timeout = timeout
        self.enabled_tools = enabled_tools or {"web_search": True, "Fetch": True}
        self._extraction_model = extraction_model
        self.verbose = verbose

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

        if self.verbose:
            print("[WebMiddleware] Initialized")
            print(f"[WebMiddleware] Searchers: {[name for name, _ in self._searchers]}")
            print(f"[WebMiddleware] Fetchers: {[name for name, _ in self._fetchers]}")

    async def _web_search_impl(
        self,
        Query: str,  # noqa: N803
        MaxResults: int | None = None,  # noqa: N803
        IncludeDomains: list[str] | None = None,  # noqa: N803
        ExcludeDomains: list[str] | None = None,  # noqa: N803
    ) -> SearchResult:
        """
        实现 web_search（多提供商降级）

        优先级：Tavily → Exa → Firecrawl
        """
        if not self._searchers:
            return SearchResult(query=Query, error="No search providers configured")

        max_results = MaxResults or self.max_search_results

        for name, searcher in self._searchers:
            try:
                result = await searcher.search(
                    query=Query,
                    max_results=max_results,
                    include_domains=IncludeDomains,
                    exclude_domains=ExcludeDomains,
                )
                if not result.error:
                    return result
                print(f"[WebMiddleware] {name} failed: {result.error}")
            except Exception as e:
                print(f"[WebMiddleware] {name} exception: {e}")

        return SearchResult(query=Query, error="All search providers failed")

    async def _fetch_impl(self, Url: str, Prompt: str) -> str:  # noqa: N803
        """
        Fetch URL content and extract information using AI.

        Priority: Jina → Markdownify for fetching, then AI extraction.
        """
        if not self._fetchers:
            return "Error: No fetch providers configured"

        fetch_result: FetchResult | None = None
        for name, fetcher in self._fetchers:
            try:
                result = await fetcher.fetch(Url)
                if not result.error:
                    fetch_result = result
                    break
                print(f"[WebMiddleware] {name} failed: {result.error}")
            except Exception as e:
                print(f"[WebMiddleware] {name} exception: {e}")

        if fetch_result is None:
            return f"Error: Failed to fetch URL: {Url}"

        content = fetch_result.content or ""
        if not content:
            return f"Error: No content retrieved from URL: {Url}"

        # Truncate if too large
        max_chars = 100_000
        if len(content) > max_chars:
            content = content[:max_chars]

        return await self._ai_extract(content, Prompt, Url)

    async def _ai_extract(self, content: str, prompt: str, url: str) -> str:
        """Use a small model to extract information from web content.

        Timeout: 30s. On failure, returns a raw content preview so the
        calling agent still has something to work with.
        """
        try:
            model = self._extraction_model
            if model is None:
                preview = content[:5000] if len(content) > 5000 else content
                return f"AI extraction unavailable. Configure an extraction model (e.g. leon:mini) in settings. Raw content:\n\n{preview}"  # noqa: E501

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

    def _get_tool_definitions(self) -> list[dict]:
        """获取工具定义"""
        return [
            {
                "type": "function",
                "function": {
                    "name": self.TOOL_WEB_SEARCH,
                    "description": "Search the web for current information. Returns titles, URLs, and snippets.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "Query": {
                                "type": "string",
                                "description": "Search query",
                            },
                            "MaxResults": {
                                "type": "integer",
                                "description": "Maximum number of results (default: 5)",
                            },
                            "IncludeDomains": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Only include results from these domains",
                            },
                            "ExcludeDomains": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Exclude results from these domains",
                            },
                        },
                        "required": ["Query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": self.TOOL_FETCH,
                    "description": "Fetch a URL and extract specific information using AI. Returns processed content, not raw HTML.",  # noqa: E501
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "Url": {
                                "type": "string",
                                "description": "URL to fetch content from",
                            },
                            "Prompt": {
                                "type": "string",
                                "description": "What information to extract from the page",
                            },
                        },
                        "required": ["Url", "Prompt"],
                    },
                },
            },
        ]

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """注入 Web 工具定义"""
        tools = list(request.tools or [])
        tools.extend(self._get_tool_definitions())
        return handler(request.override(tools=tools))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """异步：注入 Web 工具定义"""
        tools = list(request.tools or [])
        tools.extend(self._get_tool_definitions())
        return await handler(request.override(tools=tools))

    async def _handle_tool_call(self, tool_name: str, args: dict, tool_call_id: str) -> ToolMessage | None:
        """处理工具调用（异步）"""
        if tool_name == self.TOOL_WEB_SEARCH:
            result = await self._web_search_impl(
                Query=args.get("Query", ""),
                MaxResults=args.get("MaxResults"),
                IncludeDomains=args.get("IncludeDomains"),
                ExcludeDomains=args.get("ExcludeDomains"),
            )
            return ToolMessage(content=result.format_output(), tool_call_id=tool_call_id)

        elif tool_name == self.TOOL_FETCH:
            result = await self._fetch_impl(
                Url=args.get("Url", ""),
                Prompt=args.get("Prompt", ""),
            )
            return ToolMessage(content=result, tool_call_id=tool_call_id)

        return None

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        """异步：拦截并处理 Web 工具调用"""
        tool_call = request.tool_call
        tool_name = tool_call.get("name")
        args = tool_call.get("args", {})
        tool_call_id = tool_call.get("id", "")

        result = await self._handle_tool_call(tool_name, args, tool_call_id)
        if result is not None:
            return result

        return await handler(request)


__all__ = ["WebMiddleware"]
