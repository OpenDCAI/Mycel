"""Dispatcher for file reading based on file type."""

from __future__ import annotations

from pathlib import Path

from core.tools.filesystem.read.readers.binary import read_binary
from core.tools.filesystem.read.readers.notebook import read_notebook
from core.tools.filesystem.read.readers.pdf import read_pdf
from core.tools.filesystem.read.readers.pptx import read_pptx
from core.tools.filesystem.read.readers.text import read_text
from core.tools.filesystem.read.types import (
    FileType,
    ReadLimits,
    ReadResult,
    detect_file_type,
)


def read_file(
    path: Path,
    limits: ReadLimits | None = None,
    offset: int | None = None,
    limit: int | None = None,
    pages: str | None = None,
) -> ReadResult:
    """
    Read file with type-specific handling.

    Dispatches to appropriate reader based on file type:
    - TEXT: read_text with triple limits
    - BINARY: read_binary (metadata only)
    - DOCUMENT: placeholder (PDF/DOCX support planned)
    - NOTEBOOK: placeholder (.ipynb support planned)
    - ARCHIVE: placeholder (list contents planned)

    Args:
        path: Absolute path to file
        limits: ReadLimits configuration (uses defaults if None)
        offset: Start line for text files (1-indexed)
        limit: Number of lines for text files
        pages: Optional page range for document files, e.g. "1" or "3-5"

    Returns:
        ReadResult with content and metadata
    """
    if limits is None:
        limits = ReadLimits()

    if not path.exists():
        return ReadResult(
            file_path=str(path),
            file_type=FileType.TEXT,
            error=f"File not found: {path}",
        )

    if not path.is_file():
        return ReadResult(
            file_path=str(path),
            file_type=FileType.TEXT,
            error=f"Not a file: {path}",
        )

    file_type = detect_file_type(path)

    if file_type == FileType.TEXT:
        return read_text(path, limits, offset, limit)

    if file_type == FileType.BINARY:
        return read_binary(path)

    if file_type == FileType.DOCUMENT:
        start_page, limit_pages = _parse_pages_arg(pages, offset, limit)
        return _read_document(path, limits, start_page, limit_pages)

    if file_type == FileType.NOTEBOOK:
        return read_notebook(path, limits, start_cell=offset, limit_cells=limit)

    if file_type == FileType.ARCHIVE:
        return _read_archive_placeholder(path)

    return read_text(path, limits, offset, limit)


def _parse_pages_arg(
    pages: str | None,
    offset: int | None,
    limit: int | None,
) -> tuple[int | None, int | None]:
    if pages is None:
        return offset, limit

    raw = pages.strip()
    if not raw:
        raise ValueError("pages must not be empty")

    if "-" in raw:
        start_raw, end_raw = raw.split("-", 1)
        start_page = int(start_raw)
        end_page = int(end_raw)
        if start_page <= 0 or end_page < start_page:
            raise ValueError(f"Invalid pages range: {pages}")
        return start_page, end_page - start_page + 1

    start_page = int(raw)
    if start_page <= 0:
        raise ValueError(f"Invalid page number: {pages}")
    return start_page, 1


def _read_document(
    path: Path,
    limits: ReadLimits,
    start_page: int | None = None,
    limit_pages: int | None = None,
) -> ReadResult:
    """Dispatch document reading based on extension."""
    ext = path.suffix.lstrip(".").lower()

    if ext == "pdf":
        return read_pdf(path, limits, start_page, limit_pages)

    if ext in {"ppt", "pptx"}:
        return read_pptx(path, limits, start_page, limit_pages)

    stat = path.stat()
    content = (
        f"Document file: {path.name}\n"
        f"  Type: {ext.upper()}\n"
        f"  Size: {stat.st_size:,} bytes\n"
        f"\n"
        f"This document type is not yet supported.\n"
        f"Supported: PDF, PPTX"
    )
    return ReadResult(
        file_path=str(path),
        file_type=FileType.DOCUMENT,
        content=content,
        total_size=stat.st_size,
    )


def _read_archive_placeholder(path: Path) -> ReadResult:
    """Placeholder for archive reading."""
    ext = path.suffix.lstrip(".").lower()
    stat = path.stat()

    content = (
        f"Archive file: {path.name}\n  Type: {ext.upper()}\n  Size: {stat.st_size:,} bytes\n\nArchive content listing not yet implemented."
    )

    return ReadResult(
        file_path=str(path),
        file_type=FileType.ARCHIVE,
        content=content,
        total_size=stat.st_size,
    )
