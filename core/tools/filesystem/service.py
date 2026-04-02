"""FileSystem Service - registers file operation tools with ToolRegistry.

Tools:
- Read: Read file content (with chunking support)
- Write: Create new file
- Edit: Edit file (str_replace mode, supports replace_all)
- list_dir: List directory
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from core.tools.filesystem.backend import FileSystemBackend
from core.tools.filesystem.read import ReadLimits
from core.tools.filesystem.read import read_file as read_file_dispatch

if TYPE_CHECKING:
    from core.operations import FileOperationRecorder

logger = logging.getLogger(__name__)


class FileSystemService:
    """Registers filesystem tools (Read/Write/Edit/list_dir) into ToolRegistry."""

    def __init__(
        self,
        registry: ToolRegistry,
        workspace_root: str | Path,
        *,
        max_file_size: int = 10 * 1024 * 1024,
        allowed_extensions: list[str] | None = None,
        hooks: list[Any] | None = None,
        operation_recorder: FileOperationRecorder | None = None,
        backend: FileSystemBackend | None = None,
        extra_allowed_paths: list[str | Path] | None = None,
    ):
        if backend is None:
            from core.tools.filesystem.local_backend import LocalBackend

            backend = LocalBackend()

        self.backend = backend
        self.workspace_root = Path(workspace_root) if backend.is_remote else Path(workspace_root).resolve()
        self.max_file_size = max_file_size
        self.allowed_extensions = allowed_extensions
        self.hooks = hooks or []
        self._read_files: dict[Path, float | None] = {}
        self.operation_recorder = operation_recorder
        self.extra_allowed_paths: list[Path] = [Path(p) if backend.is_remote else Path(p).resolve() for p in (extra_allowed_paths or [])]

        if not backend.is_remote:
            self.workspace_root.mkdir(parents=True, exist_ok=True)

        self._register(registry)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _register(self, registry: ToolRegistry) -> None:
        registry.register(
            ToolEntry(
                name="Read",
                mode=ToolMode.INLINE,
                schema={
                    "name": "Read",
                    "description": (
                        "Read file content. Output uses cat -n format (line numbers starting at 1). "
                        "Default reads up to 2000 lines from start; use offset/limit for long files. "
                        "Supports images (PNG/JPG), PDF (use pages param for large PDFs), and Jupyter notebooks. "
                        "Path must be absolute."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Absolute file path",
                            },
                            "offset": {
                                "type": "integer",
                                "description": "Start line (1-indexed, optional)",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of lines to read (optional)",
                            },
                            "pages": {
                                "type": "string",
                                "description": "Page range for PDF files (e.g. '1-5'). Max 20 pages per request.",
                            },
                        },
                        "required": ["file_path"],
                    },
                },
                handler=self._read_file,
                source="FileSystemService",
                search_hint="read view file content text code image PDF notebook",
                is_read_only=True,
                is_concurrency_safe=True,
            )
        )

        registry.register(
            ToolEntry(
                name="Write",
                mode=ToolMode.INLINE,
                schema={
                    "name": "Write",
                    "description": (
                        "Create or overwrite a file with full content. Forces LF line endings. "
                        "Fails if file already exists — use Edit for modifications. Path must be absolute."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Absolute file path",
                            },
                            "content": {
                                "type": "string",
                                "description": "File content",
                            },
                        },
                        "required": ["file_path", "content"],
                    },
                },
                handler=self._write_file,
                source="FileSystemService",
                search_hint="create new file write content to disk",
            )
        )

        registry.register(
            ToolEntry(
                name="Edit",
                mode=ToolMode.INLINE,
                schema={
                    "name": "Edit",
                    "description": (
                        "Edit file via exact string replacement. You MUST Read the file first. "
                        "old_string must match exactly one location (or use replace_all=true). "
                        "Does not support .ipynb files (use Write to overwrite full JSON). Path must be absolute."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Absolute file path",
                            },
                            "old_string": {
                                "type": "string",
                                "description": "Exact string to replace",
                            },
                            "new_string": {
                                "type": "string",
                                "description": "Replacement string",
                            },
                            "replace_all": {
                                "type": "boolean",
                                "description": "Replace all occurrences (default: false)",
                            },
                        },
                        "required": ["file_path", "old_string", "new_string"],
                    },
                },
                handler=self._edit_file,
                source="FileSystemService",
                search_hint="edit modify replace string in existing file",
            )
        )

        registry.register(
            ToolEntry(
                name="list_dir",
                mode=ToolMode.INLINE,
                schema={
                    "name": "list_dir",
                    "description": "List directory contents (files and subdirectories, non-recursive). Path must be absolute.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory_path": {
                                "type": "string",
                                "description": "Absolute directory path",
                            },
                        },
                        "required": ["directory_path"],
                    },
                },
                handler=self._list_dir,
                source="FileSystemService",
                search_hint="list directory contents browse folder",
                is_read_only=True,
                is_concurrency_safe=True,
            )
        )

    # ------------------------------------------------------------------
    # Path validation (reused from middleware)
    # ------------------------------------------------------------------

    def _validate_path(self, path: str, operation: str) -> tuple[bool, str, Path | None]:
        if not Path(path).is_absolute():
            return False, f"Path must be absolute: {path}", None

        try:
            resolved = Path(path) if self.backend.is_remote else Path(path).resolve()
        except Exception as e:
            return False, f"Invalid path: {path} ({e})", None

        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            if not any(resolved.is_relative_to(p) for p in self.extra_allowed_paths):
                return (
                    False,
                    f"Path outside workspace\n   Workspace: {self.workspace_root}\n   Attempted: {resolved}",
                    None,
                )

        if self.allowed_extensions and resolved.suffix:
            ext = resolved.suffix.lstrip(".")
            if ext not in self.allowed_extensions:
                return (
                    False,
                    f"File type not allowed: {resolved.suffix}\n   Allowed: {', '.join(self.allowed_extensions)}",
                    None,
                )

        for hook in self.hooks:
            if hasattr(hook, "check_file_operation"):
                result = hook.check_file_operation(str(resolved), operation)
                if not result.allow:
                    return False, result.error_message, None

        return True, "", resolved

    def _check_file_staleness(self, resolved: Path) -> str | None:
        if resolved not in self._read_files:
            return "File has not been read yet. Read it first before writing to it."
        stored_mtime = self._read_files[resolved]
        if stored_mtime is None:
            return None
        current_mtime = self.backend.file_mtime(str(resolved))
        if current_mtime is not None and current_mtime != stored_mtime:
            return "File has been modified since last read. Read it again before editing."
        return None

    def _update_file_tracking(self, resolved: Path) -> None:
        self._read_files[resolved] = self.backend.file_mtime(str(resolved))

    def _record_operation(
        self,
        operation_type: str,
        file_path: str,
        before_content: str | None,
        after_content: str,
        changes: list[dict] | None = None,
    ) -> None:
        if not self.operation_recorder:
            return
        from sandbox.thread_context import get_current_run_id, get_current_thread_id

        thread_id = get_current_thread_id()
        checkpoint_id = get_current_run_id()
        if not thread_id or not checkpoint_id:
            return
        try:
            self.operation_recorder.record(
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                operation_type=operation_type,
                file_path=file_path,
                before_content=before_content,
                after_content=after_content,
                changes=changes,
            )
        except Exception as e:
            raise RuntimeError(f"[FileSystemService] Failed to record operation: {e}") from e

    def _count_lines(self, resolved: Path) -> int:
        try:
            raw = self.backend.read_file(str(resolved))
            return raw.content.count("\n") + 1
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    def _read_file(self, file_path: str, offset: int = 0, limit: int | None = None) -> str:
        is_valid, error, resolved = self._validate_path(file_path, "read")
        if not is_valid:
            return error

        file_size = self.backend.file_size(str(resolved))

        if file_size is not None and file_size > self.max_file_size:
            return f"File too large: {file_size:,} bytes (max: {self.max_file_size:,} bytes)"

        has_pagination = offset > 0 or limit is not None
        if not has_pagination and file_size is not None:
            limits = ReadLimits()
            if file_size > limits.max_size_bytes:
                total_lines = self._count_lines(resolved)
                return (
                    f"File content ({file_size:,} bytes) exceeds maximum allowed size ({limits.max_size_bytes:,} bytes).\n"
                    f"Use offset and limit parameters to read specific sections.\n"
                    f"Total lines: {total_lines}"
                )
            estimated_tokens = file_size // 4
            if estimated_tokens > limits.max_tokens:
                total_lines = self._count_lines(resolved)
                return (
                    f"File content (~{estimated_tokens:,} tokens) exceeds maximum allowed tokens ({limits.max_tokens:,}).\n"
                    f"Use offset and limit parameters to read specific sections.\n"
                    f"Total lines: {total_lines}"
                )

        from core.tools.filesystem.local_backend import LocalBackend

        if isinstance(self.backend, LocalBackend):
            limits = ReadLimits()
            result = read_file_dispatch(
                path=resolved,
                limits=limits,
                offset=offset if offset > 0 else None,
                limit=limit,
            )
            if not result.error:
                self._update_file_tracking(resolved)
            return result.format_output()

        try:
            raw = self.backend.read_file(str(resolved))
            lines = raw.content.split("\n")
            total_lines = len(lines)
            limits = ReadLimits()
            start = max(0, offset - 1) if offset > 0 else 0
            end = min(start + limit if limit else total_lines, start + limits.max_lines)
            selected = lines[start:end]
            numbered = [f"{start + i + 1:>6}\t{line}" for i, line in enumerate(selected)]
            content = "\n".join(numbered)
            self._update_file_tracking(resolved)
            return content
        except Exception as e:
            return f"Error reading file: {e}"

    def _write_file(self, file_path: str, content: str) -> str:
        is_valid, error, resolved = self._validate_path(file_path, "write")
        if not is_valid:
            return error

        if self.backend.file_exists(str(resolved)):
            return f"File already exists: {file_path}\nUse Edit to modify existing files"

        try:
            result = self.backend.write_file(str(resolved), content)
            if not result.success:
                return f"Error writing file: {result.error}"

            self._update_file_tracking(resolved)
            self._record_operation(
                operation_type="write",
                file_path=file_path,
                before_content=None,
                after_content=content,
            )

            lines = content.count("\n") + 1
            return f"File created: {file_path}\n   Lines: {lines}\n   Size: {len(content)} bytes"
        except Exception as e:
            return f"Error writing file: {e}"

    def _edit_file(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        is_valid, error, resolved = self._validate_path(file_path, "edit")
        if not is_valid:
            return error

        if not self.backend.file_exists(str(resolved)):
            return f"File not found: {file_path}"

        staleness_error = self._check_file_staleness(resolved)
        if staleness_error:
            return staleness_error

        if old_string == new_string:
            return "Error: old_string and new_string are identical (no-op edit)"

        try:
            raw = self.backend.read_file(str(resolved))
            content = raw.content

            if old_string not in content:
                return f"String not found in file\n   Looking for: {old_string[:100]}..."

            if replace_all:
                count = content.count(old_string)
                new_content = content.replace(old_string, new_string)
            else:
                count = content.count(old_string)
                if count > 1:
                    return (
                        f"String appears {count} times in file (not unique)\n"
                        f"   Use replace_all=true or provide more context to make it unique"
                    )
                new_content = content.replace(old_string, new_string, 1)
                count = 1

            result = self.backend.write_file(str(resolved), new_content)
            if not result.success:
                return f"Error editing file: {result.error}"

            self._update_file_tracking(resolved)
            self._record_operation(
                operation_type="edit",
                file_path=file_path,
                before_content=content,
                after_content=new_content,
                changes=[{"old_string": old_string, "new_string": new_string}],
            )
            return f"File edited: {file_path}\n   Replaced {count} occurrence(s)"
        except Exception as e:
            return f"Error editing file: {e}"

    def _list_dir(self, directory_path: str) -> str:
        is_valid, error, resolved = self._validate_path(directory_path, "list")
        if not is_valid:
            return error

        if not self.backend.is_dir(str(resolved)):
            if self.backend.file_exists(str(resolved)):
                return f"Not a directory: {directory_path}"
            return f"Directory not found: {directory_path}"

        try:
            result = self.backend.list_dir(str(resolved))
            if result.error:
                return f"Error listing directory: {result.error}"

            if not result.entries:
                return f"{directory_path}: Empty directory"

            items = []
            for entry in result.entries:
                if entry.is_dir:
                    count_str = f" ({entry.children_count} items)" if entry.children_count is not None else ""
                    items.append(f"\t{entry.name}/{count_str}")
                else:
                    items.append(f"\t{entry.name} ({entry.size} bytes)")

            return f"{directory_path}/\n" + "\n".join(items)
        except Exception as e:
            return f"Error listing directory: {e}"
