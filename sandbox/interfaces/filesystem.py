from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class FileReadResult:
    content: str
    size: int = 0


@dataclass
class FileWriteResult:
    success: bool
    error: str | None = None


@dataclass
class DirEntry:
    name: str
    is_dir: bool
    size: int = 0
    children_count: int | None = None  # only for directories


@dataclass
class DirListResult:
    entries: list[DirEntry] = field(default_factory=list)
    error: str | None = None


class FileSystemBackend(ABC):
    is_remote: bool = False

    @abstractmethod
    def read_file(self, path: str) -> FileReadResult: ...

    @abstractmethod
    def write_file(self, path: str, content: str) -> FileWriteResult: ...

    @abstractmethod
    def file_exists(self, path: str) -> bool: ...

    @abstractmethod
    def file_mtime(self, path: str) -> float | None: ...

    @abstractmethod
    def file_size(self, path: str) -> int | None: ...

    @abstractmethod
    def is_dir(self, path: str) -> bool: ...

    @abstractmethod
    def list_dir(self, path: str) -> DirListResult: ...
