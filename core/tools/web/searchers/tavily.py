"""Tavily searcher - AI-optimized search."""

from __future__ import annotations

import httpx

from core.tools.web.searchers.base import BaseSearcher
from core.tools.web.types import SearchItem, SearchResult


class TavilySearcher(BaseSearcher):
    """
    Searcher using Tavily API.

    Features:
    - AI-optimized search results
    - Returns relevant snippets
    - Supports domain filtering
    """

    API_URL = "https://api.tavily.com/search"

    def __init__(
        self,
        api_key: str,
        max_results: int = 5,
        timeout: int = 10,
    ):
        super().__init__(max_results, timeout)
        self.api_key = api_key

    async def search(
        self,
        query: str,
        max_results: int | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> SearchResult:
        """Search using Tavily API."""
        result = SearchResult(query=query)

        try:
            payload = {
                "api_key": self.api_key,
                "query": query,
                "max_results": max_results or self.max_results,
                "search_depth": "basic",
            }

            if include_domains:
                payload["include_domains"] = include_domains

            if exclude_domains:
                payload["exclude_domains"] = exclude_domains

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.API_URL, json=payload)
                response.raise_for_status()

            data = response.json()

            for item in data.get("results", []):
                result.results.append(
                    SearchItem(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        score=item.get("score"),
                    )
                )

            result.total_results = len(result.results)

        except httpx.TimeoutException:
            result.error = f"Timeout searching: {query}"
        except httpx.HTTPStatusError as e:
            result.error = f"Tavily API error {e.response.status_code}"
        except httpx.RequestError as e:
            result.error = f"Search error: {e}"
        except Exception as e:
            result.error = f"Unexpected error: {e}"

        return result
