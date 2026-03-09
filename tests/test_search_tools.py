"""Tests for SearchService Grep and Glob tools."""

from __future__ import annotations

import os
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
    (src / "main.py").write_text(
        "import os\nimport sys\n\ndef main():\n    print('hello world')\n"
    )
    # src/utils.py
    (src / "utils.py").write_text(
        "def helper():\n    return 42\n\ndef another():\n    return 'HELLO'\n"
    )
    # src/app.js
    (src / "app.js").write_text("const app = () => console.log('hello');\n")
    # README.md at root
    (tmp_path / "README.md").write_text("# Project\nHello World\n")
    # data.txt at root
    (tmp_path / "data.txt").write_text("line1\nline2 hello\nline3\nline4 hello\nline5\n")
    return tmp_path


@pytest.fixture()
def mw(workspace: Path) -> SearchService:
    """SearchService instance using the Python fallback (no ripgrep)."""
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
        # Python fallback format: <filepath>:<lineno>:<line>
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
        result = _grep(
            mw, pattern="HELLO", case_insensitive=True, output_mode="files_with_matches"
        )
        # Should match both utils.py ('HELLO') and data.txt ('hello')
        assert "utils.py" in result
        assert "data.txt" in result


class TestGrepContext:
    """Context lines: after_context, before_context, context."""

    def test_after_context(self, mw: SearchService, workspace: Path):
        """With ripgrep, -A adds trailing lines. Python fallback only returns matching lines."""
        # Python fallback does not support context lines, so just verify no crash
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
    """type filter parameter (Python fallback ignores type, only ripgrep uses it)."""

    def test_type_filter_no_crash(self, mw: SearchService):
        # Python fallback does not implement --type, but should not crash
        result = _grep(mw, pattern="hello", type="py")
        # Should still return results (type is ignored in Python fallback)
        assert isinstance(result, str)


class TestGrepMultiline:
    """multiline mode (Python fallback does not support it, just verify no crash)."""

    def test_multiline_no_crash(self, mw: SearchService, workspace: Path):
        result = _grep(mw, pattern="hello", multiline=True)
        assert isinstance(result, str)


class TestGrepDefaultExcludes:
    """DEFAULT_EXCLUDES directories are skipped."""

    def test_node_modules_excluded(self, mw: SearchService, workspace: Path):
        # Create a file inside node_modules
        nm = workspace / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("const hello = 'world';\n")

        result = _grep(mw, pattern="hello", output_mode="files_with_matches")
        # Check the excluded file itself is not in results
        assert str(nm / "index.js") not in result

    def test_git_excluded(self, mw: SearchService, workspace: Path):
        git_dir = workspace / ".git" / "objects"
        git_dir.mkdir(parents=True)
        (git_dir / "data").write_text("hello ref\n")

        result = _grep(mw, pattern="hello", output_mode="files_with_matches")
        assert str(git_dir / "data") not in result

    def test_pycache_excluded(self, mw: SearchService, workspace: Path):
        cache_dir = workspace / "src" / "__pycache__"
        cache_dir.mkdir(parents=True)
        (cache_dir / "main.cpython-312.pyc").write_text("hello cached\n")

        result = _grep(mw, pattern="hello", output_mode="files_with_matches")
        assert str(cache_dir / "main.cpython-312.pyc") not in result


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

    def test_all_py_files(self, mw: SearchService, workspace: Path):
        result = _glob(mw, pattern="**/*.py")
        assert "main.py" in result
        assert "utils.py" in result

    def test_all_js_files(self, mw: SearchService, workspace: Path):
        result = _glob(mw, pattern="**/*.js")
        assert "app.js" in result
        assert "main.py" not in result

    def test_md_files(self, mw: SearchService, workspace: Path):
        result = _glob(mw, pattern="*.md")
        assert "README.md" in result

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
        new_idx = next(i for i, l in enumerate(lines) if "new.txt" in l)
        mid_idx = next(i for i, l in enumerate(lines) if "mid.txt" in l)
        old_idx = next(i for i, l in enumerate(lines) if "old.txt" in l)
        assert new_idx < mid_idx < old_idx


class TestGlobDefaultExcludes:
    """DEFAULT_EXCLUDES applied to Glob as well."""

    def test_node_modules_excluded(self, mw: SearchService, workspace: Path):
        nm = workspace / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {};\n")

        result = _glob(mw, pattern="**/*.js")
        # The excluded file must not appear, but src/app.js should
        assert str(nm / "index.js") not in result
        assert "app.js" in result

    def test_venv_excluded(self, mw: SearchService, workspace: Path):
        venv = workspace / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "site.py").write_text("# site\n")

        result = _glob(mw, pattern="**/*.py")
        assert str(venv / "site.py") not in result


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

    def test_no_limits(self):
        assert SearchService._paginate("a\nb\nc", None, None) == "a\nb\nc"

    def test_head_limit_only(self):
        assert SearchService._paginate("a\nb\nc", 2, None) == "a\nb"

    def test_offset_only(self):
        assert SearchService._paginate("a\nb\nc", None, 1) == "b\nc"

    def test_both(self):
        assert SearchService._paginate("a\nb\nc\nd\ne", 2, 1) == "b\nc"

    def test_offset_beyond_lines(self):
        result = SearchService._paginate("a\nb", None, 10)
        assert result == "No matches found"


# ---------------------------------------------------------------------------
# _is_excluded
# ---------------------------------------------------------------------------


class TestIsExcluded:
    """Unit tests for _is_excluded."""

    def test_excluded_dir(self):
        assert SearchService._is_excluded(Path("/project/node_modules/pkg/index.js"))

    def test_excluded_git(self):
        assert SearchService._is_excluded(Path("/project/.git/HEAD"))

    def test_not_excluded(self):
        assert not SearchService._is_excluded(Path("/project/src/main.py"))

    def test_excluded_nested(self):
        assert SearchService._is_excluded(Path("/a/b/__pycache__/mod.pyc"))


# ---------------------------------------------------------------------------
# DEFAULT_EXCLUDES constant
# ---------------------------------------------------------------------------


class TestDefaultExcludes:
    """Verify the DEFAULT_EXCLUDES list contains essential entries."""

    def test_essential_entries(self):
        for entry in ["node_modules", ".git", "__pycache__", ".venv", "dist", "build"]:
            assert entry in DEFAULT_EXCLUDES
