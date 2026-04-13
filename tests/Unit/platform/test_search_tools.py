"""Tests for SearchService Grep and Glob tools."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.tools.search.service import DEFAULT_EXCLUDES, SearchService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with sample files for search tests."""
    # src/main.py
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("import os\nimport sys\n\ndef main():\n    print('hello world')\n")
    # src/utils.py
    (src / "utils.py").write_text("def helper():\n    return 42\n\ndef another():\n    return 'HELLO'\n")
    # src/app.js
    (src / "app.js").write_text("const app = () => console.log('hello');\n")
    # README.md at root
    (tmp_path / "README.md").write_text("# Project\nHello World\n")
    # data.txt at root
    (tmp_path / "data.txt").write_text("line1\nline2 hello\nline3\nline4 hello\nline5\n")
    return tmp_path


@pytest.fixture()
def mw(workspace: Path) -> SearchService:
    """SearchService instance using the Python implementation (no ripgrep)."""
    with patch("shutil.which", return_value=None):
        return SearchService(MagicMock(), workspace_root=workspace)


def _grep(mw: SearchService, **kwargs) -> str:
    """Shortcut: invoke _grep directly and return content."""
    return mw._grep(**kwargs)


def _glob(mw: SearchService, **kwargs) -> str:
    """Shortcut: invoke _glob directly and return content."""
    return mw._glob(**kwargs)


# ---------------------------------------------------------------------------
# Grep tests
# ---------------------------------------------------------------------------


class TestGrepFilesWithMatches:
    """Default output_mode = 'files_with_matches'."""

    def test_basic_search(self, mw: SearchService, workspace: Path):
        result = _grep(mw, pattern="hello")
        # Should match data.txt, app.js, and main.py (print('hello world'))
        assert "data.txt" in result
        assert "main.py" in result

    def test_no_matches(self, mw: SearchService):
        result = _grep(mw, pattern="zzz_nonexistent_zzz")
        assert result == "No matches found"


class TestGrepContent:
    """output_mode = 'content' returns matching lines with line numbers."""

    def test_content_mode(self, mw: SearchService, workspace: Path):
        result = _grep(mw, pattern="hello", output_mode="content")
        # Python implementation format: <filepath>:<lineno>:<line>
        assert ":2:" in result or ":5:" in result  # line2 or line5 in data.txt
        # The actual line text should be present
        assert "hello" in result

    def test_content_line_numbers(self, mw: SearchService, workspace: Path):
        # data.txt has "hello" on lines 2 and 4
        data_path = str(workspace / "data.txt")
        result = _grep(mw, pattern="hello", path=data_path, output_mode="content")
        assert f"{data_path}:2:" in result
        assert f"{data_path}:4:" in result


class TestGrepCount:
    """output_mode = 'count' returns match counts per file."""

    def test_count_mode(self, mw: SearchService, workspace: Path):
        data_path = str(workspace / "data.txt")
        result = _grep(mw, pattern="hello", path=data_path, output_mode="count")
        # data.txt has 2 lines matching "hello"
        assert f"{data_path}:2" in result

    def test_count_multiple_files(self, mw: SearchService):
        result = _grep(mw, pattern="hello", output_mode="count")
        # At least data.txt and others should appear with counts
        assert ":" in result


class TestGrepCaseInsensitive:
    """case_insensitive flag."""

    def test_case_sensitive_default(self, mw: SearchService, workspace: Path):
        # 'HELLO' is in utils.py, 'hello' is in data.txt etc.
        result = _grep(mw, pattern="HELLO", output_mode="files_with_matches")
        # Should match utils.py (has 'HELLO') but not data.txt (has lowercase 'hello')
        assert "utils.py" in result

    def test_case_insensitive(self, mw: SearchService, workspace: Path):
        result = _grep(mw, pattern="HELLO", case_insensitive=True, output_mode="files_with_matches")
        # Should match both utils.py ('HELLO') and data.txt ('hello')
        assert "utils.py" in result
        assert "data.txt" in result


class TestGrepContext:
    """Context lines: after_context, before_context, context."""

    def test_after_context(self, mw: SearchService, workspace: Path):
        """With ripgrep, -A adds trailing lines. Python implementation only returns matching lines."""
        # Python implementation does not support context lines, so just verify no crash
        result = _grep(
            mw,
            pattern="hello",
            path=str(workspace / "data.txt"),
            output_mode="content",
            after_context=1,
        )
        assert "hello" in result

    def test_before_context(self, mw: SearchService, workspace: Path):
        result = _grep(
            mw,
            pattern="hello",
            path=str(workspace / "data.txt"),
            output_mode="content",
            before_context=1,
        )
        assert "hello" in result

    def test_context_symmetric(self, mw: SearchService, workspace: Path):
        result = _grep(
            mw,
            pattern="hello",
            path=str(workspace / "data.txt"),
            output_mode="content",
            context=2,
        )
        assert "hello" in result


class TestGrepPagination:
    """head_limit and offset."""

    def test_head_limit(self, mw: SearchService, workspace: Path):
        # data.txt has 2 matching lines for "hello"
        result = _grep(
            mw,
            pattern="hello",
            path=str(workspace / "data.txt"),
            output_mode="content",
            head_limit=1,
        )
        lines = result.strip().split("\n")
        assert len(lines) == 1

    def test_offset(self, mw: SearchService, workspace: Path):
        # Get all matches first
        full = _grep(
            mw,
            pattern="hello",
            path=str(workspace / "data.txt"),
            output_mode="content",
        )
        full_lines = full.strip().split("\n")
        assert len(full_lines) == 2

        # Offset=1 should skip the first match
        result = _grep(
            mw,
            pattern="hello",
            path=str(workspace / "data.txt"),
            output_mode="content",
            offset=1,
        )
        offset_lines = result.strip().split("\n")
        assert len(offset_lines) == 1
        assert offset_lines[0] == full_lines[1]

    def test_offset_and_head_limit(self, mw: SearchService, workspace: Path):
        result = _grep(
            mw,
            pattern="line",
            path=str(workspace / "data.txt"),
            output_mode="content",
            offset=1,
            head_limit=2,
        )
        lines = result.strip().split("\n")
        assert len(lines) == 2


class TestGrepGlobFilter:
    """glob parameter filters files."""

    def test_glob_py_only(self, mw: SearchService):
        result = _grep(mw, pattern="hello", glob="*.py")
        assert "main.py" in result
        assert "app.js" not in result
        assert "data.txt" not in result

    def test_glob_js_only(self, mw: SearchService):
        result = _grep(mw, pattern="hello", glob="*.js")
        assert "app.js" in result
        assert "main.py" not in result


class TestGrepTypeFilter:
    """type filter parameter (Python implementation ignores type, only ripgrep uses it)."""

    def test_type_filter_no_crash(self, mw: SearchService):
        # Python implementation does not implement --type, but should not crash
        result = _grep(mw, pattern="hello", type="py")
        # Should still return results (type is ignored in Python implementation)
        assert isinstance(result, str)


class TestGrepMultiline:
    """multiline mode (Python implementation does not support it, just verify no crash)."""

    def test_multiline_no_crash(self, mw: SearchService, workspace: Path):
        result = _grep(mw, pattern="hello", multiline=True)
        assert isinstance(result, str)


class TestGrepRipgrepFailure:
    """ripgrep failures are not hidden by the Python implementation."""

    def test_ripgrep_exception_fails_loudly(self, workspace: Path, monkeypatch: pytest.MonkeyPatch):
        with patch("shutil.which", return_value="/usr/bin/rg"):
            service = SearchService(MagicMock(), workspace_root=workspace)

        def boom(*_args, **_kwargs):
            raise RuntimeError("rg exploded")

        python_grep = MagicMock(return_value="hidden result")
        monkeypatch.setattr(service, "_ripgrep_search", boom)
        monkeypatch.setattr(service, "_python_grep", python_grep)

        with pytest.raises(RuntimeError, match="rg exploded"):
            _grep(service, pattern="hello")

        python_grep.assert_not_called()


class TestGrepDefaultExcludes:
    """DEFAULT_EXCLUDES directories are skipped."""

    @pytest.mark.parametrize(
        ("relative_path", "content"),
        [
            ("node_modules/pkg/index.js", "const hello = 'world';\n"),
            (".git/objects/data", "hello ref\n"),
            ("src/__pycache__/main.cpython-312.pyc", "hello cached\n"),
        ],
    )
    def test_excluded_paths_do_not_appear(self, mw: SearchService, workspace: Path, relative_path: str, content: str):
        excluded = workspace / relative_path
        excluded.parent.mkdir(parents=True, exist_ok=True)
        excluded.write_text(content)

        result = _grep(mw, pattern="hello", output_mode="files_with_matches")
        assert str(excluded) not in result


class TestGrepInvalidPattern:
    """Invalid regex pattern returns an error."""

    def test_invalid_regex(self, mw: SearchService):
        result = _grep(mw, pattern="[invalid")
        assert "Invalid regex" in result or "error" in result.lower()


class TestGrepPathValidation:
    """Path validation edge cases."""

    def test_relative_path_rejected(self, mw: SearchService):
        result = _grep(mw, pattern="hello", path="relative/path")
        assert "Path must be absolute" in result

    def test_path_outside_workspace_rejected(self, mw: SearchService):
        result = _grep(mw, pattern="hello", path="/tmp/outside")
        assert "Path outside workspace" in result or "outside" in result.lower()

    def test_nonexistent_path(self, mw: SearchService, workspace: Path):
        result = _grep(mw, pattern="hello", path=str(workspace / "nonexistent"))
        assert "not found" in result.lower() or "No matches" in result


# ---------------------------------------------------------------------------
# Glob tests
# ---------------------------------------------------------------------------


class TestGlobBasic:
    """Basic glob pattern matching."""

    @pytest.mark.parametrize(
        ("pattern", "expected", "missing"),
        [
            ("**/*.py", ["main.py", "utils.py"], []),
            ("**/*.js", ["app.js"], ["main.py"]),
            ("*.md", ["README.md"], []),
        ],
    )
    def test_matching_files(self, mw: SearchService, pattern: str, expected: list[str], missing: list[str]):
        result = _glob(mw, pattern=pattern)
        for item in expected:
            assert item in result
        for item in missing:
            assert item not in result

    def test_no_matches(self, mw: SearchService):
        result = _glob(mw, pattern="**/*.xyz")
        assert result == "No files found"


class TestGlobMtimeSorting:
    """Results sorted by modification time, newest first."""

    def test_sorted_by_mtime_descending(self, mw: SearchService, workspace: Path):
        # Create files with distinct mtimes
        old = workspace / "old.txt"
        old.write_text("old")
        time.sleep(0.05)

        mid = workspace / "mid.txt"
        mid.write_text("mid")
        time.sleep(0.05)

        new = workspace / "new.txt"
        new.write_text("new")

        result = _glob(mw, pattern="*.txt")
        lines = result.strip().split("\n")

        # new.txt should appear before mid.txt, mid.txt before old.txt
        new_idx = next(i for i, line in enumerate(lines) if "new.txt" in line)
        mid_idx = next(i for i, line in enumerate(lines) if "mid.txt" in line)
        old_idx = next(i for i, line in enumerate(lines) if "old.txt" in line)
        assert new_idx < mid_idx < old_idx


class TestGlobDefaultExcludes:
    """DEFAULT_EXCLUDES applied to Glob as well."""

    @pytest.mark.parametrize(
        ("relative_path", "pattern", "visible"),
        [
            ("node_modules/pkg/index.js", "**/*.js", "app.js"),
            (".venv/lib/site.py", "**/*.py", "main.py"),
        ],
    )
    def test_excluded_paths_do_not_appear(self, mw: SearchService, workspace: Path, relative_path: str, pattern: str, visible: str):
        excluded = workspace / relative_path
        excluded.parent.mkdir(parents=True)
        excluded.write_text("excluded")

        result = _glob(mw, pattern=pattern)
        assert str(excluded) not in result
        assert visible in result


class TestGlobPathParameter:
    """path parameter defaults to workspace and validates correctly."""

    def test_defaults_to_workspace(self, mw: SearchService, workspace: Path):
        result = _glob(mw, pattern="**/*.py")
        # Should find files under workspace
        assert "main.py" in result

    def test_subdirectory(self, mw: SearchService, workspace: Path):
        result = _glob(mw, pattern="*.py", path=str(workspace / "src"))
        assert "main.py" in result
        # README.md is in root, should not appear
        assert "README" not in result

    def test_relative_path_rejected(self, mw: SearchService):
        result = _glob(mw, pattern="*.py", path="relative/dir")
        assert "Path must be absolute" in result

    def test_nonexistent_dir(self, mw: SearchService, workspace: Path):
        result = _glob(mw, pattern="*.py", path=str(workspace / "nope"))
        assert "not found" in result.lower()

    def test_file_path_rejected(self, mw: SearchService, workspace: Path):
        result = _glob(mw, pattern="*", path=str(workspace / "data.txt"))
        assert "Not a directory" in result


# ---------------------------------------------------------------------------
# _paginate
# ---------------------------------------------------------------------------


class TestPaginate:
    """Unit tests for _paginate static method."""

    @pytest.mark.parametrize(
        ("text", "head_limit", "offset", "expected"),
        [
            ("a\nb\nc", None, None, "a\nb\nc"),
            ("a\nb\nc", 2, None, "a\nb"),
            ("a\nb\nc", None, 1, "b\nc"),
            ("a\nb\nc\nd\ne", 2, 1, "b\nc"),
            ("a\nb", None, 10, "No matches found"),
        ],
    )
    def test_paginate(self, text: str, head_limit: int | None, offset: int | None, expected: str):
        assert SearchService._paginate(text, head_limit, offset) == expected


# ---------------------------------------------------------------------------
# _is_excluded
# ---------------------------------------------------------------------------


class TestIsExcluded:
    """Unit tests for _is_excluded."""

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/project/node_modules/pkg/index.js", True),
            ("/project/.git/HEAD", True),
            ("/project/src/main.py", False),
            ("/a/b/__pycache__/mod.pyc", True),
        ],
    )
    def test_paths(self, path: str, expected: bool):
        assert SearchService._is_excluded(Path(path)) is expected


# ---------------------------------------------------------------------------
# DEFAULT_EXCLUDES constant
# ---------------------------------------------------------------------------


class TestDefaultExcludes:
    """Verify the DEFAULT_EXCLUDES list contains essential entries."""

    def test_essential_entries(self):
        for entry in ["node_modules", ".git", "__pycache__", ".venv", "dist", "build"]:
            assert entry in DEFAULT_EXCLUDES
