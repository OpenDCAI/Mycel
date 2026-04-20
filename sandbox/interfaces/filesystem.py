"""FileSystem backend abstraction.

Separates I/O mechanism (local fs vs sandbox) from policy (hooks, staleness, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class FileReadResult:
    """Raw file content from backend."""

    content: str
    size: int = 0


@dataclass
class FileWriteResult:
    """Result of a write operation."""

    success: bool
    error: str | None = None


@dataclass
class DirEntry:
    """Single directory entry."""

    name: str
    is_dir: bool
    size: int = 0
    children_count: int | None = None  # only for directories


@dataclass
class DirListResult:
    """Result of listing a directory."""

    entries: list[DirEntry] = field(default_factory=list)
    error: str | None = None


class FileSystemBackend(ABC):
    """Abstract backend for filesystem I/O.

    Implementations:
    - LocalBackend: direct local filesystem access
    - Remote capability wrapper: delegates to SandboxProvider via sandbox provider/runtime
    """

    is_remote: bool = False

    @abstractmethod
    def read_file(self, path: str) -> FileReadResult:
        """Read raw file content.

        Args:
            path: Absolute file path

        Returns:
            FileReadResult with content string

        Raises:
            IOError: If file cannot be read
        """
        ...

    @abstractmethod
    def write_file(self, path: str, content: str) -> FileWriteResult:
        """Write content to file, creating parent dirs as needed.

        Args:
            path: Absolute file path
            content: File content

        Returns:
            FileWriteResult indicating success/failure
        """
        ...

    @abstractmethod
    def file_exists(self, path: str) -> bool:
        """Check if file exists."""
        ...

    @abstractmethod
    def file_mtime(self, path: str) -> float | None:
        """Get file modification time.

        Returns:
            mtime as float, or None if not available (e.g. sandbox)
        """
        ...

    @abstractmethod
    def file_size(self, path: str) -> int | None:
        """Get file size in bytes.

        Returns:
            Size in bytes, or None if not available
        """
        ...

    @abstractmethod
    def is_dir(self, path: str) -> bool:
        """Check if path is a directory."""
        ...

    @abstractmethod
    def list_dir(self, path: str) -> DirListResult:
        """List directory contents.

        Args:
            path: Absolute directory path

        Returns:
            DirListResult with entries
        """
        ...
