"""Firecrawl searcher - web crawling and search."""

from __future__ import annotations

import httpx

from core.tools.web.searchers.base import BaseSearcher
from core.tools.web.types import SearchItem, SearchResult


class FirecrawlSearcher(BaseSearcher):
    """
    Searcher using Firecrawl API.

    Features:
    - Web crawling capabilities
    - Can search and extract content
    - Crawler-backed secondary provider
    """

    API_URL = "https://api.firecrawl.dev/v1/search"

    def __init__(
        self,
        api_key: str,
        max_results: int = 5,
        timeout: int = 15,
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
        """Search using Firecrawl API."""
        result = SearchResult(query=query)

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "query": query,
                "limit": max_results or self.max_results,
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.API_URL, headers=headers, json=payload)
                response.raise_for_status()

            data = response.json()

            for item in data.get("data", []):
                url = item.get("url", "")

                if include_domains:
                    if not any(domain in url for domain in include_domains):
                        continue

                if exclude_domains:
                    if any(domain in url for domain in exclude_domains):
                        continue

                result.results.append(
                    SearchItem(
                        title=item.get("title", item.get("metadata", {}).get("title", "")),
                        url=url,
                        snippet=item.get("description", item.get("markdown", "")[:300]),
                    )
                )

            result.total_results = len(result.results)

        except httpx.TimeoutException:
            result.error = f"Timeout searching: {query}"
        except httpx.HTTPStatusError as e:
            result.error = f"Firecrawl API error {e.response.status_code}"
        except httpx.RequestError as e:
            result.error = f"Search error: {e}"
        except Exception as e:
            result.error = f"Unexpected error: {e}"

        return result
