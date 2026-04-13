"""Search Service - registers Grep and Glob tools with ToolRegistry.

Tools:
- Grep: Content search using regex (ripgrep when available, Python implementation otherwise)
- Glob: File pattern matching sorted by modification time
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema

DEFAULT_EXCLUDES: list[str] = [
    "node_modules",
    ".git",
    ".svn",
    ".hg",
    ".bzr",
    ".jj",
    ".sl",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
]


class SearchService:
    """Registers Grep and Glob tools into ToolRegistry."""

    def __init__(
        self,
        registry: ToolRegistry,
        workspace_root: str | Path,
        *,
        max_file_size: int = 10 * 1024 * 1024,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.max_file_size = max_file_size
        self.has_ripgrep = shutil.which("rg") is not None
        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        registry.register(
            ToolEntry(
                name="Grep",
                mode=ToolMode.INLINE,
                schema=make_tool_schema(
                    name="Grep",
                    description=(
                        "Regex search across files (ripgrep-based). "
                        "Default output_mode: files_with_matches (sorted by mtime). Default head_limit: 250 entries. "
                        "Auto-excludes .git/.svn/.hg dirs. Max column width 500 chars (suppresses minified/base64). "
                        "Use output_mode='content' with after_context/before_context/context for context lines."
                    ),
                    properties={
                        "pattern": {
                            "type": "string",
                            "description": "Regex pattern to search for",
                        },
                        "path": {
                            "type": "string",
                            "description": "File or directory (absolute). Defaults to workspace.",
                        },
                        "glob": {
                            "type": "string",
                            "description": "Filter files by glob (e.g., '*.py')",
                        },
                        "type": {
                            "type": "string",
                            "description": "Filter by file type (e.g., 'py', 'js')",
                        },
                        "case_insensitive": {
                            "type": "boolean",
                            "description": "Case insensitive search",
                        },
                        "after_context": {
                            "type": "integer",
                            "description": "Lines to show after each match",
                        },
                        "before_context": {
                            "type": "integer",
                            "description": "Lines to show before each match",
                        },
                        "context": {
                            "type": "integer",
                            "description": "Context lines before and after each match",
                        },
                        "output_mode": {
                            "type": "string",
                            "enum": ["content", "files_with_matches", "count"],
                            "description": "Output format. Default: files_with_matches",
                        },
                        "head_limit": {
                            "type": "integer",
                            "description": "Limit to first N entries",
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Skip first N entries",
                        },
                        "multiline": {
                            "type": "boolean",
                            "description": "Allow pattern to span multiple lines",
                        },
                        "line_numbers": {
                            "type": "boolean",
                            "description": "Show line numbers (default true). Only applies with output_mode='content'.",
                        },
                    },
                    required=["pattern"],
                ),
                handler=self._grep,
                source="SearchService",
                search_hint="search file contents regex pattern matching ripgrep",
                is_read_only=True,
                is_concurrency_safe=True,
            )
        )

        registry.register(
            ToolEntry(
                name="Glob",
                mode=ToolMode.INLINE,
                schema=make_tool_schema(
                    name="Glob",
                    description=(
                        "Fast file pattern matching (ripgrep-based). Returns paths sorted by modification time. "
                        "Includes hidden files, ignores .gitignore. Default limit 100 results. "
                        "Use '**/*.py' for recursive search. Path must be absolute."
                    ),
                    properties={
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern (e.g., '**/*.py')",
                        },
                        "path": {
                            "type": "string",
                            "description": "Directory to search (absolute). Defaults to workspace.",
                        },
                    },
                    required=["pattern"],
                ),
                handler=self._glob,
                source="SearchService",
                search_hint="find files by name glob pattern matching",
                is_read_only=True,
                is_concurrency_safe=True,
            )
        )

    # ------------------------------------------------------------------
    # Path validation
    # ------------------------------------------------------------------

    def _validate_path(self, path: str | None) -> tuple[bool, str, Path]:
        if not path:
            return True, "", self.workspace_root

        if not Path(path).is_absolute():
            return False, f"Path must be absolute: {path}", self.workspace_root

        try:
            resolved = Path(path).resolve()
        except (OSError, RuntimeError) as e:
            return False, f"Invalid path: {path} ({e})", self.workspace_root

        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            return (
                False,
                f"Path outside workspace\n  Workspace: {self.workspace_root}\n  Attempted: {resolved}",
                self.workspace_root,
            )

        return True, "", resolved

    # ------------------------------------------------------------------
    # Grep
    # ------------------------------------------------------------------

    def _grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        type: str | None = None,
        case_insensitive: bool = False,
        after_context: int | None = None,
        before_context: int | None = None,
        context: int | None = None,
        output_mode: str = "files_with_matches",
        head_limit: int | None = 250,
        offset: int | None = None,
        multiline: bool = False,
        line_numbers: bool = True,
    ) -> str:
        ok, error, resolved = self._validate_path(path)
        if not ok:
            return error

        if not resolved.exists():
            return f"Path not found: {path or self.workspace_root}"

        if self.has_ripgrep:
            return self._ripgrep_search(
                resolved,
                pattern,
                glob=glob,
                type_filter=type,
                case_insensitive=case_insensitive,
                after_context=after_context,
                before_context=before_context,
                context=context,
                output_mode=output_mode,
                head_limit=head_limit,
                offset=offset,
                multiline=multiline,
                line_numbers=line_numbers,
            )

        return self._python_grep(
            resolved,
            pattern,
            glob=glob,
            case_insensitive=case_insensitive,
            output_mode=output_mode,
            head_limit=head_limit,
            offset=offset,
        )

    def _ripgrep_search(
        self,
        path: Path,
        pattern: str,
        *,
        glob: str | None,
        type_filter: str | None,
        case_insensitive: bool,
        after_context: int | None,
        before_context: int | None,
        context: int | None,
        output_mode: str,
        head_limit: int | None,
        offset: int | None,
        multiline: bool,
        line_numbers: bool = True,
    ) -> str:
        cmd: list[str] = ["rg", pattern, str(path), "--max-columns", "500"]

        for excl in DEFAULT_EXCLUDES:
            cmd.extend(["--glob", f"!{excl}"])

        if glob:
            cmd.extend(["--glob", glob])
        if type_filter:
            cmd.extend(["--type", type_filter])
        if case_insensitive:
            cmd.append("-i")
        if multiline:
            cmd.extend(["-U", "--multiline-dotall"])

        if output_mode == "files_with_matches":
            cmd.append("--files-with-matches")
        elif output_mode == "count":
            cmd.append("--count")
        elif output_mode == "content":
            ln_flag = "--line-number" if line_numbers else "--no-line-number"
            cmd.extend([ln_flag, "--no-heading"])
            if context is not None:
                cmd.extend(["-C", str(context)])
            else:
                if after_context is not None:
                    cmd.extend(["-A", str(after_context)])
                if before_context is not None:
                    cmd.extend(["-B", str(before_context)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.workspace_root),
            )
        except subprocess.TimeoutExpired:
            return "Search timeout (30s)"

        if result.returncode not in (0, 1):
            return f"ripgrep error: {result.stderr.strip()}"

        output = result.stdout.strip()
        if not output:
            return "No matches found"

        return self._paginate(output, head_limit, offset)

    def _python_grep(
        self,
        path: Path,
        pattern: str,
        *,
        glob: str | None,
        case_insensitive: bool,
        output_mode: str,
        head_limit: int | None,
        offset: int | None,
    ) -> str:
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return f"Invalid regex: {e}"

        files = self._collect_files(path, glob)
        lines: list[str] = []

        for fp in files:
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except (PermissionError, OSError):
                continue

            if output_mode == "files_with_matches":
                if regex.search(text):
                    lines.append(str(fp))
            elif output_mode == "count":
                cnt = len(regex.findall(text))
                if cnt:
                    lines.append(f"{fp}:{cnt}")
            else:
                for i, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        lines.append(f"{fp}:{i}:{line}")

        if not lines:
            return "No matches found"

        return self._paginate("\n".join(lines), head_limit, offset)

    # ------------------------------------------------------------------
    # Glob
    # ------------------------------------------------------------------

    def _glob(self, pattern: str, path: str | None = None) -> str:
        ok, error, resolved = self._validate_path(path)
        if not ok:
            return error

        if not resolved.exists():
            return f"Path not found: {path or self.workspace_root}"

        if not resolved.is_dir():
            return f"Not a directory: {resolved}"

        matches: list[tuple[float, str]] = []
        for p in resolved.glob(pattern):
            if not p.is_file():
                continue
            if self._is_excluded(p):
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                mtime = 0.0
            matches.append((mtime, str(p)))

        if not matches:
            return "No files found"

        matches.sort(key=lambda x: x[0], reverse=True)
        return "\n".join(filepath for _, filepath in matches)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_excluded(p: Path) -> bool:
        return any(part in DEFAULT_EXCLUDES for part in p.parts)

    def _collect_files(self, path: Path, glob_pattern: str | None) -> list[Path]:
        if path.is_file():
            return [path]

        files: list[Path] = []
        for fp in path.rglob(glob_pattern or "*"):
            if not fp.is_file():
                continue
            if self._is_excluded(fp):
                continue
            if fp.stat().st_size > self.max_file_size:
                continue
            files.append(fp)
        return files

    @staticmethod
    def _paginate(output: str, head_limit: int | None, offset: int | None) -> str:
        lines = output.split("\n")
        start = offset or 0
        if start:
            lines = lines[start:]
        if head_limit and head_limit > 0:
            lines = lines[:head_limit]
        return "\n".join(lines) if lines else "No matches found"
