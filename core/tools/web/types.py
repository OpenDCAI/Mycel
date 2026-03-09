"""Types for web operations."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FetchLimits:
    """Limits for URL fetching to prevent excessive token usage."""

    max_chars: int = 100_000
    chunk_size: int = 4000
    max_chunks: int = 50

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.max_chunks <= 0:
            raise ValueError("max_chunks must be positive")


@dataclass
class ContentChunk:
    """A chunk of fetched content."""

    position: int
    content: str
    heading: str | None = None


@dataclass
class FetchResult:
    """Result of a URL fetch operation."""

    url: str
    title: str | None = None
    description: str | None = None

    content: str | None = None
    chunks: list[ContentChunk] = field(default_factory=list)

    total_chars: int = 0
    total_chunks: int = 0

    truncated: bool = False
    truncation_reason: str | None = None

    error: str | None = None

    def format_output(self) -> str:
        """Format result as string output for the agent."""
        if self.error:
            return self.error

        parts = [f"URL: {self.url}"]

        if self.title:
            parts.append(f"Title: {self.title}")

        if self.description:
            parts.append(f"Description: {self.description}")

        parts.append(f"Total chunks: {self.total_chunks}")
        parts.append(f"Total chars: {self.total_chars:,}")
        parts.append("")

        if self.chunks:
            parts.append("Content chunks:")
            for chunk in self.chunks[:5]:
                heading = f" / {chunk.heading}" if chunk.heading else ""
                parts.append(f"  - [Position: {chunk.position}]{heading}")

            if len(self.chunks) > 5:
                parts.append(f"  ... and {len(self.chunks) - 5} more chunks")

            parts.append("")
            parts.append("Use read_file tool with offset and limit to read specific sections.")

        if self.truncated:
            reason = self.truncation_reason or "limit reached"
            parts.append(f"\n[Content truncated: {reason}]")

        return "\n".join(parts)

    def get_chunk(self, position: int) -> str | None:
        """Get content of a specific chunk by position."""
        for chunk in self.chunks:
            if chunk.position == position:
                return chunk.content
        return None


@dataclass
class SearchResult:
    """Result of a web search operation."""

    query: str
    results: list[SearchItem] = field(default_factory=list)
    total_results: int = 0
    error: str | None = None

    def format_output(self) -> str:
        """Format result as string output for the agent."""
        if self.error:
            return self.error

        if not self.results:
            return f"No results found for: {self.query}"

        parts = [f"Found {len(self.results)} results for: {self.query}", ""]

        for item in self.results:
            parts.append(f"Title: {item.title}")
            parts.append(f"URL: {item.url}")
            if item.snippet:
                parts.append(f"Snippet: {item.snippet}")
            parts.append("---")

        parts.append("")
        parts.append("Use Fetch tool with a Prompt to extract specific information from URLs.")

        return "\n".join(parts)


@dataclass
class SearchItem:
    """A single search result item."""

    title: str
    url: str
    snippet: str | None = None
    score: float | None = None
