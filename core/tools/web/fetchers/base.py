from __future__ import annotations

from abc import ABC, abstractmethod

from core.tools.web.types import FetchLimits, FetchResult


class BaseFetcher(ABC):
    def __init__(self, limits: FetchLimits | None = None, timeout: int = 10):
        self.limits = limits or FetchLimits()
        self.timeout = timeout

    @abstractmethod
    async def fetch(self, url: str) -> FetchResult: ...

    def _split_into_chunks(self, content: str, headings: list[str] | None = None) -> list[tuple[int, str, str | None]]:
        chunks: list[tuple[int, str, str | None]] = []
        chunk_size = self.limits.chunk_size

        if len(content) <= chunk_size:
            chunks.append((0, content, None))
            return chunks

        lines = content.split("\n")
        current_chunk: list[str] = []
        current_size = 0
        current_heading: str | None = None
        position = 0

        for line in lines:
            line_size = len(line) + 1

            is_heading = line.startswith("#") or (headings and any(h in line for h in headings))

            if current_size + line_size > chunk_size and current_chunk:
                chunk_content = "\n".join(current_chunk)
                chunks.append((position, chunk_content, current_heading))
                position += 1
                current_chunk = []
                current_size = 0

                if position >= self.limits.max_chunks:
                    break

            if is_heading:
                current_heading = line.lstrip("#").strip()[:50]

            current_chunk.append(line)
            current_size += line_size

        if current_chunk and position < self.limits.max_chunks:
            chunk_content = "\n".join(current_chunk)
            chunks.append((position, chunk_content, current_heading))

        return chunks
