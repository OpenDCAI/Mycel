"""PDF file reader using pymupdf (optional dependency)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.tools.filesystem.read.types import FileType, ReadLimits, ReadResult

_pymupdf: Any | None = None

try:
    import pymupdf as _pymupdf

    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


def read_pdf(
    path: Path,
    limits: ReadLimits,
    start_page: int | None = None,
    limit_pages: int | None = None,
) -> ReadResult:
    """
    Read PDF file with page-based pagination.

    Args:
        path: Absolute path to PDF file
        limits: ReadLimits configuration (max_chars applies to total output)
        start_page: Start page (1-indexed, None = start from page 1)
        limit_pages: Number of pages to read (None = default 10 pages)

    Returns:
        ReadResult with extracted text and metadata
    """
    if not HAS_PYMUPDF:
        return _no_pymupdf_result(path)
    if _pymupdf is None:
        raise RuntimeError("pymupdf import unexpectedly unavailable")

    stat = path.stat()
    result = ReadResult(
        file_path=str(path),
        file_type=FileType.DOCUMENT,
        total_size=stat.st_size,
    )

    try:
        doc = _pymupdf.open(path)
    except Exception as e:
        result.error = f"Error opening PDF: {e}"
        return result

    total_pages = len(doc)
    result.total_pages = total_pages

    start_idx = (start_page - 1) if start_page and start_page > 0 else 0
    if start_idx >= total_pages:
        doc.close()
        result.error = f"Start page {start_page} exceeds total pages {total_pages}"
        return result

    effective_limit = limit_pages if limit_pages else 10
    end_idx = min(start_idx + effective_limit, total_pages)

    output_parts: list[str] = []
    total_chars = 0
    truncated = False
    truncation_reason: str | None = None
    pages_read = 0

    for page_num in range(start_idx, end_idx):
        page = doc[page_num]
        text = page.get_text()

        page_header = f"\n{'=' * 60}\nPage {page_num + 1}/{total_pages}\n{'=' * 60}\n"

        if total_chars + len(page_header) + len(text) > limits.max_chars:
            truncated = True
            truncation_reason = f"max_chars={limits.max_chars}"
            remaining = limits.max_chars - total_chars - len(page_header)
            if remaining > 100:
                output_parts.append(page_header)
                output_parts.append(text[:remaining] + "\n... [truncated]")
                pages_read += 1
            break

        output_parts.append(page_header)
        output_parts.append(text)
        total_chars += len(page_header) + len(text)
        pages_read += 1

    doc.close()

    if end_idx < total_pages and not truncated:
        truncated = True
        truncation_reason = f"limit_pages={effective_limit}"

    result.content = "".join(output_parts)
    result.start_page = start_idx + 1
    result.end_page = start_idx + pages_read
    result.truncated = truncated
    result.truncation_reason = truncation_reason

    return result


def _no_pymupdf_result(path: Path) -> ReadResult:
    """Return result when pymupdf is not installed."""
    stat = path.stat()
    content = (
        f"PDF file: {path.name}\n  Size: {stat.st_size:,} bytes\n\npymupdf is not installed. To read PDF files:\n  uv pip install pymupdf"
    )
    return ReadResult(
        file_path=str(path),
        file_type=FileType.DOCUMENT,
        content=content,
        total_size=stat.st_size,
    )
