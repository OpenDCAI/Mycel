"""Markdownify fetcher - local HTML to Markdown conversion."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import httpx

from core.tools.web.fetchers.base import BaseFetcher
from core.tools.web.types import ContentChunk, FetchLimits, FetchResult

md: Callable[..., str] | None = None
try:
    from markdownify import markdownify as md

    HAS_MARKDOWNIFY = True
except ImportError:
    HAS_MARKDOWNIFY = False

BeautifulSoup: Any | None = None
try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class MarkdownifyFetcher(BaseFetcher):
    """
    Fetcher using markdownify for HTML to Markdown conversion.

    Falls back to BeautifulSoup text extraction if markdownify unavailable.
    """

    def __init__(
        self,
        limits: FetchLimits | None = None,
        timeout: int = 10,
        user_agent: str = _BROWSER_UA,
    ):
        super().__init__(limits, timeout)
        self.user_agent = user_agent
        self.has_markdownify = HAS_MARKDOWNIFY
        self.has_bs4 = HAS_BS4

    async def _do_fetch(self, url: str, verify: bool = True) -> httpx.Response:
        """Fetch URL with explicit timeout and redirect following."""
        timeout = httpx.Timeout(self.timeout, connect=5.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=verify,
        ) as client:
            response = await client.get(url, headers={"User-Agent": self.user_agent})
            response.raise_for_status()
            return response

    async def fetch(self, url: str) -> FetchResult:
        """Fetch URL content and convert to Markdown."""
        result = FetchResult(url=url)

        try:
            try:
                response = await self._do_fetch(url, verify=True)
            except httpx.ConnectError as e:
                # Only retry without SSL verify for certificate-related errors
                cause = str(e.__cause__) if e.__cause__ else str(e)
                if "ssl" in cause.lower() or "certificate" in cause.lower():
                    response = await self._do_fetch(url, verify=False)
                else:
                    raise

            content_type = response.headers.get("Content-Type", "")

            if "text/html" in content_type:
                content = self._process_html(response.text, result)
            else:
                content = response.text

            if len(content) > self.limits.max_chars:
                content = content[: self.limits.max_chars]
                result.truncated = True
                result.truncation_reason = f"max_chars={self.limits.max_chars}"

            result.total_chars = len(content)

            chunk_data = self._split_into_chunks(content)
            result.chunks = [ContentChunk(position=pos, content=cont, heading=head) for pos, cont, head in chunk_data]
            result.total_chunks = len(result.chunks)

            result.content = content

        except httpx.TimeoutException:
            result.error = f"Timeout fetching URL ({self.timeout}s): {url}"
        except httpx.HTTPStatusError as e:
            result.error = f"HTTP error {e.response.status_code}: {url}"
        except httpx.RequestError as e:
            result.error = f"Error fetching URL: {e}"

        return result

    def _process_html(self, html: str, result: FetchResult) -> str:
        """Process HTML content to Markdown or plain text."""
        if self.has_markdownify:
            return self._markdownify_html(html, result)
        if self.has_bs4:
            return self._bs4_extract(html, result)
        return self._basic_extract(html, result)

    def _markdownify_html(self, html: str, result: FetchResult) -> str:
        """Convert HTML to Markdown using markdownify."""
        if md is None:
            raise RuntimeError("markdownify import unexpectedly unavailable")
        if self.has_bs4:
            if BeautifulSoup is None:
                raise RuntimeError("BeautifulSoup import unexpectedly unavailable")
            soup = BeautifulSoup(html, "html.parser")

            title_tag = soup.find("title")
            if title_tag:
                result.title = title_tag.get_text(strip=True)

            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                result.description = og_desc["content"]

            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            main_content = soup.find("main") or soup.find("article") or soup.find("div", class_="content") or soup.find("body")

            if main_content:
                html = str(main_content)

        content = md(
            html,
            heading_style="ATX",
            bullets="-",
            strip=["script", "style", "nav", "footer", "header", "aside"],
        )

        content = re.sub(r"\n{3,}", "\n\n", content)
        return content.strip()

    def _bs4_extract(self, html: str, result: FetchResult) -> str:
        """Extract text using BeautifulSoup."""
        if BeautifulSoup is None:
            raise RuntimeError("BeautifulSoup import unexpectedly unavailable")
        soup = BeautifulSoup(html, "html.parser")

        title_tag = soup.find("title")
        if title_tag:
            result.title = title_tag.get_text(strip=True)

        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            result.description = og_desc["content"]

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        main_content = soup.find("main") or soup.find("article") or soup.find("div", class_="content") or soup.find("body")

        if main_content:
            text = main_content.get_text(separator="\n\n", strip=True)
        else:
            text = soup.get_text(separator="\n\n", strip=True)

        return re.sub(r"\n{3,}", "\n\n", text)

    def _basic_extract(self, html: str, result: FetchResult) -> str:
        """Basic HTML extraction without external libraries."""
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_match:
            result.title = title_match.group(1).strip()

        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()
