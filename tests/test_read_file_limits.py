"""Tests for read_file hard-reject mode and ReadLimits validation.

Covers:
- ReadLimits default values and validation
- FileSystemMiddleware._read_file_impl hard-reject logic:
  - Small file without offset -> normal return
  - Large file (>256KB) without offset -> hard reject
  - Large file with offset/limit -> normal return (bypass)
  - Very large file (>10MB) with offset/limit -> still rejected (absolute limit)
  - Token estimation rejection (file <256KB but >25K estimated tokens)
  - Error messages include guidance to use offset/limit
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.tools.filesystem.middleware import FileSystemMiddleware
from core.tools.filesystem.read.types import ReadLimits
from sandbox.interfaces.filesystem import FileReadResult, FileSystemBackend

# ---------------------------------------------------------------------------
# ReadLimits tests
# ---------------------------------------------------------------------------


class TestReadLimitsDefaults:
    """Verify ReadLimits default values."""

    def test_default_max_lines(self):
        limits = ReadLimits()
        assert limits.max_lines == 2000

    def test_default_max_chars(self):
        limits = ReadLimits()
        assert limits.max_chars == 200_000

    def test_default_max_size_bytes(self):
        limits = ReadLimits()
        assert limits.max_size_bytes == 256_000

    def test_default_max_tokens(self):
        limits = ReadLimits()
        assert limits.max_tokens == 25_000

    def test_default_max_line_length(self):
        limits = ReadLimits()
        assert limits.max_line_length == 2000


class TestReadLimitsValidation:
    """Verify that negative/zero values raise ValueError."""

    def test_negative_max_lines(self):
        with pytest.raises(ValueError, match="max_lines must be positive"):
            ReadLimits(max_lines=-1)

    def test_zero_max_lines(self):
        with pytest.raises(ValueError, match="max_lines must be positive"):
            ReadLimits(max_lines=0)

    def test_negative_max_chars(self):
        with pytest.raises(ValueError, match="max_chars must be positive"):
            ReadLimits(max_chars=-5)

    def test_zero_max_chars(self):
        with pytest.raises(ValueError, match="max_chars must be positive"):
            ReadLimits(max_chars=0)

    def test_negative_max_line_length(self):
        with pytest.raises(ValueError, match="max_line_length must be positive"):
            ReadLimits(max_line_length=-1)

    def test_negative_max_size_bytes(self):
        with pytest.raises(ValueError, match="max_size_bytes must be positive"):
            ReadLimits(max_size_bytes=-1)

    def test_zero_max_size_bytes(self):
        with pytest.raises(ValueError, match="max_size_bytes must be positive"):
            ReadLimits(max_size_bytes=0)

    def test_negative_max_tokens(self):
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            ReadLimits(max_tokens=-10)

    def test_zero_max_tokens(self):
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            ReadLimits(max_tokens=0)

    def test_positive_values_accepted(self):
        limits = ReadLimits(
            max_lines=1,
            max_chars=1,
            max_line_length=1,
            max_size_bytes=1,
            max_tokens=1,
        )
        assert limits.max_lines == 1


# ---------------------------------------------------------------------------
# Helper: mock FileSystemBackend
# ---------------------------------------------------------------------------


def _make_mock_backend(
    *,
    file_size: int | None = 100,
    file_content: str = "line1\nline2\nline3\n",
    file_mtime: float | None = 1000.0,
) -> MagicMock:
    """Create a mock FileSystemBackend with sensible defaults."""
    backend = MagicMock(spec=FileSystemBackend)
    backend.is_remote = False
    backend.file_size.return_value = file_size
    backend.file_exists.return_value = True
    backend.file_mtime.return_value = file_mtime
    backend.read_file.return_value = FileReadResult(content=file_content, size=len(file_content))
    backend.is_dir.return_value = False
    return backend


def _make_middleware(workspace: Path, backend: MagicMock) -> FileSystemMiddleware:
    """Create a FileSystemMiddleware with mocked backend, suppressing init output."""
    return FileSystemMiddleware(
        workspace_root=workspace,
        backend=backend,
        verbose=False,
    )


# ---------------------------------------------------------------------------
# read_file hard-reject tests
# ---------------------------------------------------------------------------


class TestReadFileSmallFile:
    """Small file (<256KB) without offset -> normal return."""

    def test_small_file_returns_content(self, tmp_path: Path):
        content = "hello\nworld\n"
        backend = _make_mock_backend(file_size=len(content), file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "small.txt")
        result = mw._read_file_impl(file_path)

        # Should NOT have an error
        assert result.error is None
        # Backend read_file should have been called (through the remote path
        # since our mock is not a real LocalBackend)
        backend.read_file.assert_called()

    def test_small_file_has_content(self, tmp_path: Path):
        content = "abc\ndef\n"
        backend = _make_mock_backend(file_size=len(content), file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "small.txt")
        result = mw._read_file_impl(file_path)

        assert result.content is not None
        assert "abc" in result.content


class TestReadFileLargeFileHardReject:
    """Large file (>256KB) without offset -> hard reject."""

    def test_large_file_no_offset_rejected(self, tmp_path: Path):
        large_size = 300_000  # > 256_000
        backend = _make_mock_backend(file_size=large_size, file_content="x" * large_size)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "big.txt")
        result = mw._read_file_impl(file_path)

        assert result.error is not None
        assert "exceeds maximum allowed size" in result.error

    def test_large_file_error_contains_file_size(self, tmp_path: Path):
        large_size = 300_000
        backend = _make_mock_backend(file_size=large_size, file_content="x" * large_size)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "big.txt")
        result = mw._read_file_impl(file_path)

        assert f"{large_size:,}" in result.error

    def test_large_file_error_contains_total_lines(self, tmp_path: Path):
        large_size = 300_000
        # Content with known line count
        lines = ["line"] * 5000
        content = "\n".join(lines)
        backend = _make_mock_backend(file_size=large_size, file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "big.txt")
        result = mw._read_file_impl(file_path)

        assert result.error is not None
        assert "Total lines:" in result.error

    def test_large_file_error_suggests_offset_limit(self, tmp_path: Path):
        large_size = 300_000
        backend = _make_mock_backend(file_size=large_size, file_content="x" * large_size)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "big.txt")
        result = mw._read_file_impl(file_path)

        assert "offset" in result.error.lower()
        assert "limit" in result.error.lower()


class TestReadFileLargeFileWithPagination:
    """Large file + with offset/limit -> normal return (bypass hard-reject)."""

    def test_large_file_with_offset_allowed(self, tmp_path: Path):
        large_size = 300_000  # > 256_000 but < 10MB
        content = "\n".join([f"line {i}" for i in range(5000)])
        backend = _make_mock_backend(file_size=large_size, file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "big.txt")
        result = mw._read_file_impl(file_path, offset=1, limit=100)

        # Should NOT be rejected by the hard-reject layer
        assert result.error is None

    def test_large_file_with_limit_only_allowed(self, tmp_path: Path):
        large_size = 300_000
        content = "\n".join([f"line {i}" for i in range(5000)])
        backend = _make_mock_backend(file_size=large_size, file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "big.txt")
        result = mw._read_file_impl(file_path, offset=0, limit=50)

        # limit is set, so has_pagination = True
        assert result.error is None


class TestReadFileAbsoluteLimit:
    """Very large file (>10MB) + with offset/limit -> still rejected."""

    def test_very_large_file_always_rejected(self, tmp_path: Path):
        huge_size = 11 * 1024 * 1024  # 11MB > 10MB default max_file_size
        backend = _make_mock_backend(file_size=huge_size)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "huge.bin")
        result = mw._read_file_impl(file_path, offset=1, limit=10)

        assert result.error is not None
        assert "too large" in result.error.lower()

    def test_very_large_file_error_shows_size(self, tmp_path: Path):
        huge_size = 15 * 1024 * 1024
        backend = _make_mock_backend(file_size=huge_size)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "huge.bin")
        result = mw._read_file_impl(file_path)

        assert result.error is not None
        assert f"{huge_size:,}" in result.error

    def test_very_large_file_no_offset_also_rejected(self, tmp_path: Path):
        huge_size = 11 * 1024 * 1024
        backend = _make_mock_backend(file_size=huge_size)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "huge.bin")
        result = mw._read_file_impl(file_path)

        assert result.error is not None
        assert "too large" in result.error.lower()


class TestReadFileTokenEstimation:
    """File <256KB but >25K estimated tokens -> rejected without pagination."""

    def test_token_estimation_rejects(self, tmp_path: Path):
        # Token estimation: file_size // 4
        # To exceed 25_000 tokens, need file_size > 100_000 bytes
        # But also need file_size <= 256_000 to not hit the size-bytes check first
        file_size = 120_000  # 120KB < 256KB, but 120_000 // 4 = 30_000 > 25_000
        content = "a" * file_size
        backend = _make_mock_backend(file_size=file_size, file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "many_tokens.txt")
        result = mw._read_file_impl(file_path)

        assert result.error is not None
        assert "tokens" in result.error.lower()
        assert "exceeds maximum allowed tokens" in result.error

    def test_token_estimation_shows_estimated_count(self, tmp_path: Path):
        file_size = 120_000
        expected_tokens = file_size // 4  # 30,000
        content = "a" * file_size
        backend = _make_mock_backend(file_size=file_size, file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "many_tokens.txt")
        result = mw._read_file_impl(file_path)

        assert result.error is not None
        assert f"{expected_tokens:,}" in result.error

    def test_token_estimation_suggests_offset_limit(self, tmp_path: Path):
        file_size = 120_000
        content = "a" * file_size
        backend = _make_mock_backend(file_size=file_size, file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "many_tokens.txt")
        result = mw._read_file_impl(file_path)

        assert result.error is not None
        assert "offset" in result.error.lower()
        assert "limit" in result.error.lower()

    def test_token_estimation_bypass_with_pagination(self, tmp_path: Path):
        file_size = 120_000
        content = "\n".join([f"line {i}" for i in range(3000)])
        backend = _make_mock_backend(file_size=file_size, file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "many_tokens.txt")
        result = mw._read_file_impl(file_path, offset=1, limit=100)

        # Pagination bypasses token estimation check
        assert result.error is None

    def test_file_under_token_limit_passes(self, tmp_path: Path):
        # file_size = 80_000 -> 80_000 // 4 = 20_000 tokens < 25_000
        file_size = 80_000
        content = "a" * file_size
        backend = _make_mock_backend(file_size=file_size, file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "ok_tokens.txt")
        result = mw._read_file_impl(file_path)

        # Should pass both size and token checks
        assert result.error is None


class TestReadFileBoundaryConditions:
    """Edge cases around the boundary values."""

    def test_exactly_at_size_limit_passes(self, tmp_path: Path):
        # Exactly 256_000 bytes should NOT trigger (check is >)
        file_size = 256_000
        # 256_000 // 4 = 64_000 tokens > 25_000 -> will be caught by token check
        # Use a size that passes both: need file_size <= 256_000 AND file_size // 4 <= 25_000
        # 25_000 * 4 = 100_000. So use exactly 100_000.
        file_size = 100_000
        content = "a" * file_size
        backend = _make_mock_backend(file_size=file_size, file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "exact.txt")
        result = mw._read_file_impl(file_path)

        assert result.error is None

    def test_one_byte_over_size_limit_rejected(self, tmp_path: Path):
        file_size = 256_001
        content = "x" * file_size
        backend = _make_mock_backend(file_size=file_size, file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "over.txt")
        result = mw._read_file_impl(file_path)

        assert result.error is not None
        assert "exceeds maximum allowed size" in result.error

    def test_file_size_none_skips_hard_reject(self, tmp_path: Path):
        """When backend returns None for file_size, skip all size-based checks."""
        content = "a" * 500_000  # Would normally be rejected
        backend = _make_mock_backend(file_size=None, file_content=content)
        mw = _make_middleware(tmp_path, backend)

        file_path = str(tmp_path / "unknown_size.txt")
        result = mw._read_file_impl(file_path)

        # file_size is None, so both absolute limit and hard-reject are skipped
        assert result.error is None
