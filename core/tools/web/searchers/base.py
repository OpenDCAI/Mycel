from __future__ import annotations

from abc import ABC, abstractmethod

from core.tools.web.types import SearchResult


class BaseSearcher(ABC):
    def __init__(self, max_results: int = 5, timeout: int = 10):
        self.max_results = max_results
        self.timeout = timeout

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> SearchResult: ...
