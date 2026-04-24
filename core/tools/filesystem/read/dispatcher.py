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
        stat = path.stat()
        ext = path.suffix.lstrip(".").lower()
        content = (
            f"Archive file: {path.name}\n"
            f"  Type: {ext.upper()}\n"
            f"  Size: {stat.st_size:,} bytes\n\n"
            f"Archive content listing not yet implemented."
        )
        return ReadResult(
            file_path=str(path),
            file_type=FileType.ARCHIVE,
            content=content,
            total_size=stat.st_size,
        )

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
