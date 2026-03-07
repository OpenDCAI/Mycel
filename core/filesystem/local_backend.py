"""Local filesystem backend - direct local I/O."""

from __future__ import annotations

from pathlib import Path

from core.filesystem.backend import (
    DirEntry,
    DirListResult,
    FileReadResult,
    FileSystemBackend,
    FileWriteResult,
)


class LocalBackend(FileSystemBackend):
    """Backend that operates directly on the local filesystem."""

    def read_file(self, path: str) -> FileReadResult:
        p = Path(path)
        content = p.read_text(encoding="utf-8")
        return FileReadResult(content=content, size=p.stat().st_size)

    def write_file(self, path: str, content: str) -> FileWriteResult:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return FileWriteResult(success=True)
        except Exception as e:
            return FileWriteResult(success=False, error=str(e))

    def file_exists(self, path: str) -> bool:
        return Path(path).exists()

    def file_mtime(self, path: str) -> float | None:
        try:
            return Path(path).stat().st_mtime
        except OSError:
            return None

    def file_size(self, path: str) -> int | None:
        try:
            return Path(path).stat().st_size
        except OSError:
            return None

    def is_dir(self, path: str) -> bool:
        return Path(path).is_dir()

    def list_dir(self, path: str) -> DirListResult:
        import os
        try:
            p = Path(path)
            entries = []
            for item in sorted(p.iterdir()):
                if not os.access(item, os.R_OK):
                    continue
                if item.is_file():
                    entries.append(DirEntry(name=item.name, is_dir=False, size=item.stat().st_size))
                elif item.is_dir():
                    count = sum(1 for _ in item.iterdir())
                    entries.append(DirEntry(name=item.name, is_dir=True, children_count=count))
            return DirListResult(entries=entries)
        except Exception as e:
            return DirListResult(error=str(e))
