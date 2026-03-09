"""Fetchers subpackage - handles URL content fetching with multiple strategies."""

from core.tools.web.fetchers.base import BaseFetcher
from core.tools.web.fetchers.jina import JinaFetcher
from core.tools.web.fetchers.markdownify import MarkdownifyFetcher

__all__ = ["BaseFetcher", "JinaFetcher", "MarkdownifyFetcher"]
