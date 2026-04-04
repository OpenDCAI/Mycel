from __future__ import annotations

from pathlib import Path
import threading
import time

from core.runtime.registry import ToolRegistry
from core.tools.filesystem.service import FileSystemService, _ReadFileStateCache
from sandbox.interfaces.filesystem import DirListResult, FileReadResult, FileSystemBackend, FileWriteResult


def _make_service(
    workspace: Path,
    *,
    max_read_cache_entries: int = 100,
    max_edit_file_size: int | None = None,
) -> FileSystemService:
    return FileSystemService(
        registry=ToolRegistry(),
        workspace_root=workspace,
        max_read_cache_entries=max_read_cache_entries,
        max_edit_file_size=max_edit_file_size,
    )


def test_edit_rejects_if_last_read_was_partial_view(tmp_path: Path):
    service = _make_service(tmp_path)
    target = tmp_path / "sample.txt"
    target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    read_result = service._read_file(str(target), offset=2, limit=1)
    assert "<file" in read_result

    edit_result = service._edit_file(
        str(target),
        old_string="beta",
        new_string="BETA",
    )

    assert "full file" in edit_result.lower()
    assert "read" in edit_result.lower()
    assert target.read_text(encoding="utf-8") == "alpha\nbeta\ngamma\n"


def test_edit_allows_read_that_covered_entire_file_with_offset_one(tmp_path: Path):
    service = _make_service(tmp_path)
    target = tmp_path / "sample.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")

    read_result = service._read_file(str(target), offset=1, limit=2000)
    assert "<file" in read_result

    edit_result = service._edit_file(
        str(target),
        old_string="beta",
        new_string="BETA",
    )

    assert "File edited" in edit_result
    assert target.read_text(encoding="utf-8") == "alpha\nBETA\n"


def test_edit_rejects_notebook_files_even_after_read(tmp_path: Path):
    service = _make_service(tmp_path)
    target = tmp_path / "nb.ipynb"
    target.write_text('{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}\n', encoding="utf-8")

    read_result = service._read_file(str(target))
    assert "nb.ipynb" in read_result

    edit_result = service._edit_file(
        str(target),
        old_string="[]",
        new_string='[{"cell_type":"markdown","source":["hi"]}]',
    )

    assert "ipynb" in edit_result.lower()
    assert "write" in edit_result.lower()


def test_write_normalizes_crlf_to_lf(tmp_path: Path):
    service = _make_service(tmp_path)
    target = tmp_path / "created.txt"

    result = service._write_file(str(target), "a\r\nb\r\n")

    assert "File created" in result
    assert target.read_bytes() == b"a\nb\n"


def test_write_overwrites_existing_file_with_full_replacement(tmp_path: Path):
    service = _make_service(tmp_path)
    target = tmp_path / "existing.txt"
    target.write_text("old\r\ncontent\r\n", encoding="utf-8")

    result = service._write_file(str(target), "new\r\ncontent\r\n")

    assert "File created" in result
    assert target.read_bytes() == b"new\ncontent\n"


def test_read_tracking_lru_eviction_restores_read_before_edit_gate(tmp_path: Path):
    service = _make_service(tmp_path, max_read_cache_entries=2)

    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    third = tmp_path / "third.txt"
    for path in (first, second, third):
        path.write_text(f"{path.stem}\n", encoding="utf-8")

    assert "<file" in service._read_file(str(first))
    assert "<file" in service._read_file(str(second))
    assert "<file" in service._read_file(str(third))

    edit_result = service._edit_file(
        str(first),
        old_string="first",
        new_string="FIRST",
    )

    assert "read" in edit_result.lower()
    assert "full file" in edit_result.lower()
    assert first.read_text(encoding="utf-8") == "first\n"


def test_edit_preserves_crlf_line_endings(tmp_path: Path):
    service = _make_service(tmp_path)
    target = tmp_path / "windows.txt"
    target.write_bytes(b"alpha\r\nbeta\r\n")

    assert "<file" in service._read_file(str(target))

    edit_result = service._edit_file(
        str(target),
        old_string="beta",
        new_string="BETA",
    )

    assert "File edited" in edit_result
    assert target.read_bytes() == b"alpha\r\nBETA\r\n"


def test_edit_with_empty_old_string_creates_missing_file(tmp_path: Path):
    service = _make_service(tmp_path)
    target = tmp_path / "created-via-edit.txt"

    edit_result = service._edit_file(
        str(target),
        old_string="",
        new_string="hello\n",
    )

    assert "File created" in edit_result
    assert target.read_text(encoding="utf-8") == "hello\n"


def test_edit_rejects_file_larger_than_edit_cap(tmp_path: Path):
    service = _make_service(tmp_path, max_edit_file_size=8)
    target = tmp_path / "large.txt"
    target.write_text("123456789\n", encoding="utf-8")

    assert "<file" in service._read_file(str(target))

    edit_result = service._edit_file(
        str(target),
        old_string="123",
        new_string="abc",
    )

    assert "too large" in edit_result.lower()
    assert "8" in edit_result


def test_default_edit_size_cap_matches_default_read_size_cap(tmp_path: Path):
    service = FileSystemService(
        registry=ToolRegistry(),
        workspace_root=tmp_path,
    )

    assert service.max_edit_file_size == service.max_file_size


def test_read_state_cache_clone_is_independent(tmp_path: Path):
    first = (tmp_path / "a.txt").resolve()
    cache = _ReadFileStateCache(max_entries=2)
    cache.set(first, state=cache.make_state(timestamp=1.0, is_partial=False))

    clone = cache.clone()
    second = (tmp_path / "b.txt").resolve()
    clone.set(second, state=clone.make_state(timestamp=2.0, is_partial=True))

    assert cache.get(first) is not None
    assert cache.get(second) is None
    assert clone.get(second) is not None


def test_read_state_cache_merge_prefers_newer_timestamp(tmp_path: Path):
    target = (tmp_path / "shared.txt").resolve()
    older = _ReadFileStateCache(max_entries=2)
    older.set(target, state=older.make_state(timestamp=1.0, is_partial=False))

    newer = _ReadFileStateCache(max_entries=2)
    newer.set(target, state=newer.make_state(timestamp=2.0, is_partial=True))

    older.merge(newer)

    merged = older.get(target)
    assert merged is not None
    assert merged.timestamp == 2.0
    assert merged.is_partial is True


def test_edit_rechecks_staleness_inside_critical_section(tmp_path: Path):
    class RacingBackend(FileSystemBackend):
        is_remote = False

        def __init__(self):
            self._mtime = 1.0
            self._content = "alpha\nbeta\n"
            self.writes: list[str] = []

        def read_file(self, path: str) -> FileReadResult:
            before = self._content
            self._content = "alpha\nEXTERNAL\n"
            self._mtime = 2.0
            return FileReadResult(content=before, size=len(before))

        def write_file(self, path: str, content: str) -> FileWriteResult:
            self.writes.append(content)
            self._content = content
            return FileWriteResult(success=True)

        def file_exists(self, path: str) -> bool:
            return True

        def file_mtime(self, path: str) -> float | None:
            return self._mtime

        def file_size(self, path: str) -> int | None:
            return len(self._content.encode("utf-8"))

        def is_dir(self, path: str) -> bool:
            return False

        def list_dir(self, path: str) -> DirListResult:
            return DirListResult(entries=[])

    backend = RacingBackend()
    service = FileSystemService(
        registry=ToolRegistry(),
        workspace_root=tmp_path,
        backend=backend,
    )
    target = (tmp_path / "race.txt").resolve()
    service._read_files.set(
        target,
        state=service._read_files.make_state(timestamp=1.0, is_partial=False),
    )

    edit_result = service._edit_file(
        str(target),
        old_string="beta",
        new_string="BETA",
    )

    assert "modified since last read" in edit_result
    assert backend.writes == []
    assert backend._content == "alpha\nEXTERNAL\n"

def test_concurrent_edits_do_not_both_commit_from_same_stale_read(tmp_path: Path):
    class ConcurrentBackend(FileSystemBackend):
        is_remote = False

        def __init__(self):
            self._mtime = 1.0
            self._content = "alpha\nbeta\n"
            self._write_lock = threading.Lock()
            self.writes: list[str] = []

        def read_file(self, path: str) -> FileReadResult:
            return FileReadResult(content=self._content, size=len(self._content))

        def write_file(self, path: str, content: str) -> FileWriteResult:
            time.sleep(0.05)
            with self._write_lock:
                self.writes.append(content)
                self._content = content
                self._mtime += 1.0
            return FileWriteResult(success=True)

        def file_exists(self, path: str) -> bool:
            return True

        def file_mtime(self, path: str) -> float | None:
            return self._mtime

        def file_size(self, path: str) -> int | None:
            return len(self._content.encode("utf-8"))

        def is_dir(self, path: str) -> bool:
            return False

        def list_dir(self, path: str) -> DirListResult:
            return DirListResult(entries=[])

    backend = ConcurrentBackend()
    service = FileSystemService(
        registry=ToolRegistry(),
        workspace_root=tmp_path,
        backend=backend,
    )
    target = (tmp_path / "race.txt").resolve()
    service._read_files.set(
        target,
        state=service._read_files.make_state(timestamp=1.0, is_partial=False),
    )

    results: list[str] = []

    def run_edit(new_string: str) -> None:
        results.append(
            service._edit_file(
                str(target),
                old_string="beta",
                new_string=new_string,
            )
        )

    t1 = threading.Thread(target=run_edit, args=("BETA-ONE",))
    t2 = threading.Thread(target=run_edit, args=("BETA-TWO",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    success_count = sum("File edited" in result for result in results)
    failure_count = sum(
        ("modified since last read" in result) or ("String not found in file" in result)
        for result in results
    )

    assert success_count == 1
    assert failure_count == 1
    assert len(backend.writes) == 1


def test_remote_edit_does_not_trust_false_negative_exists_probe(tmp_path: Path):
    class FlakyRemoteBackend(FileSystemBackend):
        is_remote = True

        def __init__(self):
            self._content = "result = 3\n"
            self.writes: list[str] = []

        def read_file(self, path: str) -> FileReadResult:
            return FileReadResult(content=self._content, size=len(self._content))

        def write_file(self, path: str, content: str) -> FileWriteResult:
            self.writes.append(content)
            self._content = content
            return FileWriteResult(success=True)

        def file_exists(self, path: str) -> bool:
            return False

        def file_mtime(self, path: str) -> float | None:
            return None

        def file_size(self, path: str) -> int | None:
            return len(self._content.encode("utf-8"))

        def is_dir(self, path: str) -> bool:
            return False

        def list_dir(self, path: str) -> DirListResult:
            return DirListResult(entries=[])

    backend = FlakyRemoteBackend()
    service = FileSystemService(
        registry=ToolRegistry(),
        workspace_root=Path("/home/daytona"),
        backend=backend,
    )
    target = Path("/home/daytona/interleave.py")
    service._read_files.set(
        target,
        state=service._read_files.make_state(timestamp=None, is_partial=False),
    )

    edit_result = service._edit_file(
        str(target),
        old_string="result = 3",
        new_string="result = 5",
    )

    assert "File edited" in edit_result
    assert backend.writes == ["result = 5\n"]
