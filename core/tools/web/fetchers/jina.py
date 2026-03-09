"""Jina Reader fetcher - best quality content extraction."""

from __future__ import annotations

import httpx

from core.tools.web.fetchers.base import BaseFetcher
from core.tools.web.types import ContentChunk, FetchLimits, FetchResult


class JinaFetcher(BaseFetcher):
    """
    Fetcher using Jina Reader API.

    Features:
    - Returns clean Markdown directly
    - Automatically removes ads, navigation, etc.
    - Supports PDF extraction
    """

    READER_BASE_URL = "https://r.jina.ai/"

    def __init__(
        self,
        api_key: str,
        limits: FetchLimits | None = None,
        timeout: int = 15,
    ):
        super().__init__(limits, timeout)
        self.api_key = api_key

    async def fetch(self, url: str) -> FetchResult:
        """Fetch URL content using Jina Reader API."""
        result = FetchResult(url=url)

        try:
            reader_url = f"{self.READER_BASE_URL}{url}"

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "X-Return-Format": "markdown",
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(reader_url, headers=headers)
                response.raise_for_status()

            content = response.text

            if len(content) > self.limits.max_chars:
                content = content[: self.limits.max_chars]
                result.truncated = True
                result.truncation_reason = f"max_chars={self.limits.max_chars}"

            result.total_chars = len(content)

            title_line = content.split("\n")[0] if content else None
            if title_line and title_line.startswith("#"):
                result.title = title_line.lstrip("#").strip()

            chunk_data = self._split_into_chunks(content)
            result.chunks = [ContentChunk(position=pos, content=cont, heading=head) for pos, cont, head in chunk_data]
            result.total_chunks = len(result.chunks)

            result.content = content

        except httpx.TimeoutException:
            result.error = f"Timeout fetching URL: {url}"
        except httpx.HTTPStatusError as e:
            result.error = f"HTTP error {e.response.status_code}: {url}"
        except httpx.RequestError as e:
            result.error = f"Error fetching URL: {e}"

        return result
