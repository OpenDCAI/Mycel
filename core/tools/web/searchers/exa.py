"""Exa searcher - semantic AI search."""

from __future__ import annotations

import httpx

from core.tools.web.searchers.base import BaseSearcher
from core.tools.web.types import SearchItem, SearchResult


class ExaSearcher(BaseSearcher):
    """
    Searcher using Exa API.

    Features:
    - Semantic AI-powered search
    - Good for academic/deep content
    - Neural search capabilities
    """

    API_URL = "https://api.exa.ai/search"

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
        """Search using Exa API."""
        result = SearchResult(query=query)

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "query": query,
                "numResults": max_results or self.max_results,
                "type": "neural",
                "useAutoprompt": True,
                "contents": {
                    "text": {"maxCharacters": 500},
                },
            }

            if include_domains:
                payload["includeDomains"] = include_domains

            if exclude_domains:
                payload["excludeDomains"] = exclude_domains

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.API_URL, headers=headers, json=payload)
                response.raise_for_status()

            data = response.json()

            for item in data.get("results", []):
                result.results.append(
                    SearchItem(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("text", ""),
                        score=item.get("score"),
                    )
                )

            result.total_results = len(result.results)

        except httpx.TimeoutException:
            result.error = f"Timeout searching: {query}"
        except httpx.HTTPStatusError as e:
            result.error = f"Exa API error {e.response.status_code}"
        except httpx.RequestError as e:
            result.error = f"Search error: {e}"
        except Exception as e:
            result.error = f"Unexpected error: {e}"

        return result
