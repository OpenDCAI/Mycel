"""Types for file reading operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class FileType(Enum):
    """Supported file types."""

    TEXT = "text"
    BINARY = "binary"
    DOCUMENT = "document"
    NOTEBOOK = "notebook"
    ARCHIVE = "archive"


@dataclass
class ReadLimits:
    """Limits for file reading to prevent excessive token usage.

    Two layers of limits:
    - max_size_bytes / max_tokens: Hard-reject when no offset/limit specified (bypassed with offset/limit)
    - max_lines / max_chars: Per-read limits (always enforced)
    """

    max_lines: int = 2000
    max_chars: int = 200_000
    max_line_length: int = 2000
    max_size_bytes: int = 256_000
    max_tokens: int = 25_000

    def __post_init__(self) -> None:
        if self.max_lines <= 0:
            raise ValueError("max_lines must be positive")
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if self.max_line_length <= 0:
            raise ValueError("max_line_length must be positive")
        if self.max_size_bytes <= 0:
            raise ValueError("max_size_bytes must be positive")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")


@dataclass
class ReadResult:
    """Result of a file read operation."""

    file_path: str
    file_type: FileType

    content: str | None = None
    content_blocks: list[dict[str, str]] | None = None

    total_size: int = 0
    total_lines: int | None = None
    total_pages: int | None = None
    total_cells: int | None = None

    start_line: int | None = None
    end_line: int | None = None
    start_page: int | None = None
    end_page: int | None = None

    truncated: bool = False
    truncation_reason: str | None = None

    error: str | None = None

    def format_output(self) -> str:
        """Format result as string output for the agent."""
        if self.error:
            return self.error

        if self.content is None:
            return f"No content available for {self.file_path}"

        parts = [
            f'<file name="{self.file_path}" '
            f'start_line="{self.start_line or 1}" '
            f'end_line="{self.end_line or self.total_lines or 0}" '
            f'full_length="{self.total_lines or 0}">'
        ]
        parts.append(self.content)
        parts.append("</file>")

        if self.truncated:
            reason = self.truncation_reason or "limit reached"
            parts.append(f"\n\nFile truncated ({reason}). Use offset and limit parameters to read more.")

        return "\n".join(parts)


TEXT_EXTENSIONS: set[str] = {
    "py",
    "pyi",
    "pyx",
    "js",
    "jsx",
    "ts",
    "tsx",
    "mjs",
    "cjs",
    "java",
    "kt",
    "kts",
    "scala",
    "c",
    "h",
    "cpp",
    "hpp",
    "cc",
    "cxx",
    "go",
    "rs",
    "swift",
    "m",
    "mm",
    "rb",
    "php",
    "pl",
    "pm",
    "sh",
    "bash",
    "zsh",
    "fish",
    "sql",
    "graphql",
    "gql",
    "html",
    "htm",
    "xml",
    "xhtml",
    "svg",
    "css",
    "scss",
    "sass",
    "less",
    "json",
    "yaml",
    "yml",
    "toml",
    "ini",
    "cfg",
    "conf",
    "md",
    "markdown",
    "rst",
    "txt",
    "text",
    "env",
    "gitignore",
    "dockerignore",
    "editorconfig",
    "makefile",
    "dockerfile",
    "r",
    "rmd",
    "jl",
    "lua",
    "vim",
    "el",
    "tf",
    "tfvars",
    "hcl",
    "proto",
    "thrift",
    "avsc",
    "csv",
    "tsv",
    "lock",
}

BINARY_EXTENSIONS: set[str] = {
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
    "mp3",
    "wav",
    "ogg",
    "flac",
    "aac",
    "m4a",
    "mp4",
    "avi",
    "mov",
    "mkv",
    "webm",
    "flv",
    "exe",
    "dll",
    "so",
    "dylib",
    "bin",
    "pyc",
    "pyo",
    "class",
    "o",
    "obj",
    "woff",
    "woff2",
    "ttf",
    "otf",
    "eot",
    "db",
    "sqlite",
    "sqlite3",
}

DOCUMENT_EXTENSIONS: set[str] = {
    "pdf",
    "doc",
    "docx",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
    "odt",
    "ods",
    "odp",
}

NOTEBOOK_EXTENSIONS: set[str] = {
    "ipynb",
}

ARCHIVE_EXTENSIONS: set[str] = {
    "zip",
    "tar",
    "gz",
    "bz2",
    "xz",
    "7z",
    "rar",
    "tgz",
    "tbz2",
    "txz",
    "jar",
    "war",
    "ear",
    "whl",
    "egg",
}


def detect_file_type(path: Path) -> FileType:
    """Detect file type based on extension."""
    ext = path.suffix.lstrip(".").lower()

    if not ext:
        return FileType.TEXT

    if ext in TEXT_EXTENSIONS:
        return FileType.TEXT
    if ext in BINARY_EXTENSIONS:
        return FileType.BINARY
    if ext in DOCUMENT_EXTENSIONS:
        return FileType.DOCUMENT
    if ext in NOTEBOOK_EXTENSIONS:
        return FileType.NOTEBOOK
    if ext in ARCHIVE_EXTENSIONS:
        return FileType.ARCHIVE

    return FileType.TEXT
