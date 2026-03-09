"""Binary file reader - returns metadata or image content blocks."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from core.tools.filesystem.read.types import FileType, ReadResult

IMAGE_EXTENSIONS: set[str] = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "bmp",
    "webp",
    "ico",
    "tiff",
    "heic",
    "heif",
}

MAX_IMAGE_SIZE: int = 20 * 1024 * 1024  # 20MB


def read_binary(path: Path) -> ReadResult:
    """
    Read binary file.

    For image files, returns content_blocks with base64-encoded image data.
    For other binary files, returns metadata only.

    Args:
        path: Absolute path to file

    Returns:
        ReadResult with content_blocks for images, or metadata text for other binaries
    """
    stat = path.stat()
    mime_type, _ = mimetypes.guess_type(str(path))
    ext = path.suffix.lstrip(".").lower()

    if ext in IMAGE_EXTENSIONS:
        return _read_image(path, stat.st_size, mime_type or f"image/{ext}")

    size_str = _format_size(stat.st_size)
    content_lines = [
        f"Binary file: {path.name}",
        f"  Type: {mime_type or 'unknown'}",
        f"  Extension: .{ext}" if ext else "  Extension: (none)",
        f"  Size: {size_str} ({stat.st_size:,} bytes)",
    ]

    return ReadResult(
        file_path=str(path),
        file_type=FileType.BINARY,
        content="\n".join(content_lines),
        total_size=stat.st_size,
        truncated=False,
    )


def _read_image(path: Path, size: int, mime_type: str) -> ReadResult:
    """Read image file and return as content block."""
    if size > MAX_IMAGE_SIZE:
        return ReadResult(
            file_path=str(path),
            file_type=FileType.BINARY,
            content=f"Image too large: {_format_size(size)} (max: {_format_size(MAX_IMAGE_SIZE)})",
            total_size=size,
            error=f"Image exceeds size limit: {size} bytes",
        )

    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")

    return ReadResult(
        file_path=str(path),
        file_type=FileType.BINARY,
        content_blocks=[
            {
                "type": "image",
                "mime_type": mime_type,
                "base64": encoded,
            }
        ],
        total_size=size,
        truncated=False,
    )


def _format_size(size: int) -> str:
    """Format file size in human-readable form."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        size //= 1024
    return f"{size:.1f} TB"
