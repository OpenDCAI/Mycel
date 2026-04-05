"""FileSystem Service - registers file operation tools with ToolRegistry.

Tools:
- Read: Read file content (with chunking support)
- Write: Create new file
- Edit: Edit file (str_replace mode, supports replace_all)
- list_dir: List directory
"""

from __future__ import annotations

import logging
import tempfile
import threading
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema
from core.runtime.tool_result import ToolResultEnvelope, tool_success
from core.tools.filesystem.backend import FileSystemBackend
from core.tools.filesystem.read import ReadLimits
from core.tools.filesystem.read import read_file as read_file_dispatch
from core.tools.filesystem.read.readers.binary import IMAGE_EXTENSIONS, MAX_IMAGE_SIZE
from core.tools.filesystem.read.types import FileType, detect_file_type

if TYPE_CHECKING:
    from core.operations import FileOperationRecorder

logger = logging.getLogger(__name__)
DEFAULT_READ_STATE_CACHE_SIZE = 100
ABSOLUTE_PATH_PATTERN = r"^(?:/|[A-Za-z]:[\\/])"
type ResolvedPath = Path | PurePosixPath
type ValidationResult = tuple[Literal[True], str, ResolvedPath] | tuple[Literal[False], str, None]


def _remote_path(path: str | Path) -> PurePosixPath:
    # @@@remote-posix-path-contract - Remote filesystem tools operate on sandbox
    # POSIX paths, not host-native paths. Preserve forward-slash semantics even
    # when the host process is running on Windows.
    return PurePosixPath(str(path).replace("\\", "/"))


@dataclass
class _ReadFileState:
    timestamp: float | None
    is_partial: bool


class _ReadFileStateCache:
    def __init__(self, max_entries: int = DEFAULT_READ_STATE_CACHE_SIZE):
        self._max_entries = max_entries
        self._entries: OrderedDict[ResolvedPath, _ReadFileState] = OrderedDict()

    @staticmethod
    def make_state(*, timestamp: float | None, is_partial: bool) -> _ReadFileState:
        return _ReadFileState(timestamp=timestamp, is_partial=is_partial)

    def get(self, path: ResolvedPath) -> _ReadFileState | None:
        state = self._entries.get(path)
        if state is None:
            return None
        self._entries.move_to_end(path)
        return state

    def set(self, path: ResolvedPath, state: _ReadFileState) -> None:
        self._entries[path] = state
        self._entries.move_to_end(path)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def clone(self) -> _ReadFileStateCache:
        clone = _ReadFileStateCache(max_entries=self._max_entries)
        clone._entries = OrderedDict(
            (path, _ReadFileState(timestamp=state.timestamp, is_partial=state.is_partial)) for path, state in self._entries.items()
        )
        return clone

    def merge(self, other: _ReadFileStateCache) -> None:
        for path, incoming in other._entries.items():
            existing = self._entries.get(path)
            if existing is None or self._is_newer(incoming, existing):
                self.set(
                    path,
                    _ReadFileState(timestamp=incoming.timestamp, is_partial=incoming.is_partial),
                )

    @staticmethod
    def _is_newer(incoming: _ReadFileState, existing: _ReadFileState) -> bool:
        if incoming.timestamp is None:
            return False
        if existing.timestamp is None:
            return True
        return incoming.timestamp >= existing.timestamp


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
        extra_allowed_paths: Sequence[str | Path] | None = None,
        max_read_cache_entries: int = DEFAULT_READ_STATE_CACHE_SIZE,
        max_edit_file_size: int | None = None,
    ):
        if backend is None:
            from core.tools.filesystem.local_backend import LocalBackend

            backend = LocalBackend()

        self.backend = backend
        self.workspace_root: ResolvedPath = _remote_path(workspace_root) if backend.is_remote else Path(workspace_root).resolve()
        self.max_file_size = max_file_size
        self.allowed_extensions = allowed_extensions
        self.hooks = hooks or []
        self._read_files = _ReadFileStateCache(max_entries=max_read_cache_entries)
        self.max_edit_file_size = max_file_size if max_edit_file_size is None else max_edit_file_size
        self.operation_recorder = operation_recorder
        self.extra_allowed_paths = [_remote_path(p) if backend.is_remote else Path(p).resolve() for p in (extra_allowed_paths or [])]
        self._edit_critical_section = threading.Lock()

        if not backend.is_remote and isinstance(self.workspace_root, Path):
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
                schema=make_tool_schema(
                    name="Read",
                    description=(
                        "Read file content. Output uses cat -n format (line numbers starting at 1). "
                        "Default reads up to 2000 lines from start; use offset/limit for long files. "
                        "Supports images (PNG/JPG), PDF (use pages param for large PDFs), and Jupyter notebooks. "
                        "Path must be absolute."
                    ),
                    properties={
                        "file_path": {
                            "type": "string",
                            "description": "Absolute file path",
                            "minLength": 1,
                            "pattern": ABSOLUTE_PATH_PATTERN,
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
                    required=["file_path"],
                ),
                handler=self._read_file,
                validate_input=self._validate_read_args,
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
                schema=make_tool_schema(
                    name="Write",
                    description="Create or overwrite a file with full content. Forces LF line endings. Path must be absolute.",
                    properties={
                        "file_path": {
                            "type": "string",
                            "description": "Absolute file path",
                            "minLength": 1,
                            "pattern": ABSOLUTE_PATH_PATTERN,
                        },
                        "content": {
                            "type": "string",
                            "description": "File content",
                        },
                    },
                    required=["file_path", "content"],
                ),
                handler=self._write_file,
                validate_input=self._validate_write_args,
                source="FileSystemService",
                search_hint="create new file write content to disk",
            )
        )

        registry.register(
            ToolEntry(
                name="Edit",
                mode=ToolMode.INLINE,
                schema=make_tool_schema(
                    name="Edit",
                    description=(
                        "Edit file via exact string replacement. You MUST Read the file first. "
                        "old_string must match exactly one location (or use replace_all=true). "
                        "Does not support .ipynb files (use Write to overwrite full JSON). Path must be absolute."
                    ),
                    properties={
                        "file_path": {
                            "type": "string",
                            "description": "Absolute file path",
                            "minLength": 1,
                            "pattern": ABSOLUTE_PATH_PATTERN,
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
                    required=["file_path", "old_string", "new_string"],
                ),
                handler=self._edit_file,
                validate_input=self._validate_edit_args,
                source="FileSystemService",
                search_hint="edit modify replace string in existing file",
            )
        )

        registry.register(
            ToolEntry(
                name="list_dir",
                mode=ToolMode.INLINE,
                schema=make_tool_schema(
                    name="list_dir",
                    description="List directory contents (files and subdirectories, non-recursive). Path must be absolute.",
                    properties={
                        "path": {
                            "type": "string",
                            "description": "Absolute directory path",
                            "minLength": 1,
                            "pattern": ABSOLUTE_PATH_PATTERN,
                        },
                    },
                    required=["path"],
                ),
                handler=self._list_dir,
                validate_input=self._validate_list_dir_args,
                source="FileSystemService",
                search_hint="list directory contents browse folder",
                is_read_only=True,
                is_concurrency_safe=True,
            )
        )

    # ------------------------------------------------------------------
    # Path validation (reused from middleware)
    # ------------------------------------------------------------------

    def _validate_path(self, path: str, operation: str) -> ValidationResult:
        if self.backend.is_remote:
            if not _remote_path(path).is_absolute():
                return False, f"Path must be absolute: {path}", None
        elif not Path(path).is_absolute():
            return False, f"Path must be absolute: {path}", None

        try:
            resolved = _remote_path(path) if self.backend.is_remote else Path(path).resolve()
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

    def _validation_error(self, message: str, error_code: str) -> dict[str, object]:
        return {
            "result": False,
            "message": message,
            "errorCode": error_code,
        }

    def _path_validation_error(self, message: str) -> dict[str, object]:
        # @@@filesystem-validation-codes - Keep the pre-execution path failure
        # mapping centralized so the runner can surface stable structured
        # codes instead of ad-hoc handler strings on the highest-traffic tools.
        if message.startswith("Path must be absolute:"):
            return self._validation_error(message, "PATH_NOT_ABSOLUTE")
        if message.startswith("Invalid path:"):
            return self._validation_error(message, "INVALID_PATH")
        if message.startswith("Path outside workspace"):
            return self._validation_error(message, "PATH_OUTSIDE_WORKSPACE")
        if message.startswith("File type not allowed:"):
            return self._validation_error(message, "FILE_TYPE_NOT_ALLOWED")
        return self._validation_error(message, "INVALID_PATH")

    def _validate_existing_path(self, path: str, operation: str) -> tuple[dict[str, object] | None, ResolvedPath | None]:
        is_valid, error, resolved = self._validate_path(path, operation)
        if not is_valid:
            return self._path_validation_error(error), None
        assert resolved is not None
        return None, resolved

    def _validation_message(self, error: dict[str, object]) -> str:
        return str(error["message"])

    def _read_preflight(
        self,
        *,
        file_path: str,
        offset: int = 0,
        limit: int | None = None,
        pages: str | None = None,
    ) -> tuple[dict[str, object] | None, ResolvedPath | None]:
        error, resolved = self._validate_existing_path(file_path, "read")
        if error is not None:
            return error, None
        assert resolved is not None

        file_size = self.backend.file_size(str(resolved))
        if file_size is not None and file_size > self.max_file_size:
            return (
                self._validation_error(
                    f"File too large: {file_size:,} bytes (max: {self.max_file_size:,} bytes)",
                    "FILE_TOO_LARGE",
                ),
                None,
            )

        has_pagination = offset > 0 or limit is not None or pages is not None
        if not has_pagination and file_size is not None:
            limits = ReadLimits()
            if file_size > limits.max_size_bytes:
                total_lines = self._count_lines(resolved)
                return (
                    self._validation_error(
                        (
                            f"File content ({file_size:,} bytes) exceeds maximum allowed size ({limits.max_size_bytes:,} bytes).\n"
                            f"Use offset and limit parameters to read specific sections.\n"
                            f"Total lines: {total_lines}"
                        ),
                        "READ_REQUIRES_PAGINATION",
                    ),
                    None,
                )
            estimated_tokens = file_size // 4
            if estimated_tokens > limits.max_tokens:
                total_lines = self._count_lines(resolved)
                return (
                    self._validation_error(
                        (
                            f"File content (~{estimated_tokens:,} tokens) exceeds maximum allowed tokens ({limits.max_tokens:,}).\n"
                            f"Use offset and limit parameters to read specific sections.\n"
                            f"Total lines: {total_lines}"
                        ),
                        "READ_REQUIRES_PAGINATION",
                    ),
                    None,
                )

        return None, resolved

    def _edit_preflight(self, *, file_path: str) -> tuple[dict[str, object] | None, ResolvedPath | None]:
        error, resolved = self._validate_existing_path(file_path, "edit")
        if error is not None:
            return error, None
        assert resolved is not None

        if resolved.suffix.lower() == ".ipynb":
            return (
                self._validation_error(
                    "Notebook files (.ipynb) are not supported by Edit. Use Write to overwrite the full JSON.",
                    "NOTEBOOK_EDIT_UNSUPPORTED",
                ),
                None,
            )

        file_size = self.backend.file_size(str(resolved))
        if file_size is not None and file_size > self.max_edit_file_size:
            return (
                self._validation_error(
                    f"File too large for Edit: {file_size:,} bytes (max: {self.max_edit_file_size:,} bytes)",
                    "FILE_TOO_LARGE",
                ),
                None,
            )

        return None, resolved

    def _list_dir_preflight(self, *, path: str) -> tuple[dict[str, object] | None, ResolvedPath | None]:
        error, resolved = self._validate_existing_path(path, "list")
        if error is not None:
            return error, None
        assert resolved is not None
        if not self.backend.is_dir(str(resolved)):
            if self.backend.file_exists(str(resolved)):
                return self._validation_error(f"Not a directory: {path}", "NOT_A_DIRECTORY"), None
            return self._validation_error(f"Directory not found: {path}", "DIRECTORY_NOT_FOUND"), None
        return None, resolved

    def _validate_read_args(self, args: dict[str, Any], request: Any) -> dict[str, Any]:
        error, _ = self._read_preflight(
            file_path=args["file_path"],
            offset=args.get("offset") or 0,
            limit=args.get("limit"),
            pages=args.get("pages"),
        )
        return error or args

    def _validate_write_args(self, args: dict[str, Any], request: Any) -> dict[str, Any]:
        error, _ = self._validate_existing_path(args["file_path"], "write")
        return error or args

    def _validate_edit_args(self, args: dict[str, Any], request: Any) -> dict[str, Any]:
        error, _ = self._edit_preflight(file_path=args["file_path"])
        return error or args

    def _validate_list_dir_args(self, args: dict[str, Any], request: Any) -> dict[str, Any]:
        error, _ = self._list_dir_preflight(path=args["path"])
        return error or args

    def _check_file_staleness(self, resolved: ResolvedPath) -> str | None:
        state = self._read_files.get(resolved)
        if state is None:
            return "File has not been read yet. Read the full file first before editing."
        if state.is_partial:
            return "File has only been read partially. Read the full file before editing."
        stored_mtime = state.timestamp
        if stored_mtime is None:
            return None
        current_mtime = self.backend.file_mtime(str(resolved))
        if current_mtime is not None and current_mtime != stored_mtime:
            return "File has been modified since last read. Read it again before editing."
        return None

    def _update_file_tracking(
        self,
        resolved: ResolvedPath,
        *,
        is_partial: bool,
        file_type: FileType | None = None,
    ) -> None:
        if file_type is None:
            file_type = self._detect_file_type(resolved)
        if file_type not in {FileType.TEXT, FileType.NOTEBOOK}:
            return
        self._read_files.set(
            resolved,
            _ReadFileState(
                timestamp=self.backend.file_mtime(str(resolved)),
                is_partial=is_partial,
            ),
        )

    def _normalize_write_content(self, content: str) -> str:
        return content.replace("\r\n", "\n").replace("\r", "\n")

    def _read_result_is_partial(self, result) -> bool:
        if getattr(result, "truncated", False):
            return True
        if getattr(result, "file_type", None) == FileType.TEXT:
            start_line = getattr(result, "start_line", None) or 1
            total_lines = getattr(result, "total_lines", None)
            end_line = getattr(result, "end_line", None) or total_lines or start_line
            if total_lines is not None:
                return start_line > 1 or end_line < total_lines
        return False

    def _detect_file_type(self, resolved: ResolvedPath) -> FileType:
        return detect_file_type(Path(str(resolved)))

    def _structured_media_success(
        self,
        *,
        resolved: ResolvedPath,
        file_type: FileType,
        content_blocks: list[dict[str, str]],
    ) -> ToolResultEnvelope:
        return tool_success(
            [
                {
                    "type": "text",
                    "text": (f"Read file: {resolved.name}\nSpecial content is attached below as structured blocks."),
                },
                *content_blocks,
            ],
            metadata={"file_type": file_type.value},
        )

    def _restore_special_result_identity(
        self,
        *,
        result,
        resolved: ResolvedPath,
        temp_path: Path,
    ) -> None:
        result.file_path = str(resolved)
        if isinstance(getattr(result, "content", None), str):
            result.content = result.content.replace(str(temp_path), str(resolved)).replace(temp_path.name, resolved.name)

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

    def _count_lines(self, resolved: ResolvedPath) -> int:
        try:
            raw = self.backend.read_file(str(resolved))
            return raw.content.count("\n") + 1
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    def _read_file(self, file_path: str, offset: int = 0, limit: int | None = None, pages: str | None = None) -> str | ToolResultEnvelope:
        error, resolved = self._read_preflight(
            file_path=file_path,
            offset=offset,
            limit=limit,
            pages=pages,
        )
        if error is not None:
            return self._validation_message(error)
        assert resolved is not None

        from core.tools.filesystem.local_backend import LocalBackend

        if isinstance(self.backend, LocalBackend):
            assert isinstance(resolved, Path)
            limits = ReadLimits()
            result = read_file_dispatch(
                path=resolved,
                limits=limits,
                offset=offset if offset > 0 else None,
                limit=limit,
                pages=pages,
            )
            if not result.error:
                self._update_file_tracking(
                    resolved,
                    is_partial=self._read_result_is_partial(result),
                    file_type=result.file_type,
                )
            if result.content_blocks:
                return self._structured_media_success(
                    resolved=resolved,
                    file_type=result.file_type,
                    content_blocks=result.content_blocks,
                )
            return result.format_output()

        try:
            file_type = self._detect_file_type(resolved)
            download_bytes = getattr(self.backend, "download_bytes", None)
            if callable(download_bytes) and file_type in {FileType.BINARY, FileType.DOCUMENT}:
                # @@@dt-02-remote-special-file-bridge
                # Remote providers expose raw-byte download hooks. Reuse the
                # same local dispatcher for binary/document reads instead of
                # degrading special files into placeholder text.
                raw_bytes = download_bytes(str(resolved))
                if not isinstance(raw_bytes, (bytes, bytearray)):
                    raise TypeError(f"Remote special-file download returned {type(raw_bytes).__name__}, expected bytes.")
                raw_bytes = bytes(raw_bytes)
                if (
                    file_type == FileType.BINARY
                    and resolved.suffix.lstrip(".").lower() in IMAGE_EXTENSIONS
                    and len(raw_bytes) > MAX_IMAGE_SIZE
                ):
                    return f"Image exceeds size limit: {len(raw_bytes)} bytes"
                with tempfile.NamedTemporaryFile(suffix=resolved.suffix, delete=False) as tmp:
                    tmp.write(raw_bytes)
                    tmp_path = Path(tmp.name)
                try:
                    result = read_file_dispatch(
                        path=tmp_path,
                        limits=ReadLimits(),
                        offset=offset if offset > 0 else None,
                        limit=limit,
                        pages=pages,
                    )
                finally:
                    tmp_path.unlink(missing_ok=True)
                self._restore_special_result_identity(
                    result=result,
                    resolved=resolved,
                    temp_path=tmp_path,
                )
                if result.content_blocks:
                    return self._structured_media_success(
                        resolved=resolved,
                        file_type=result.file_type,
                        content_blocks=result.content_blocks,
                    )
                return result.format_output()
            raw = self.backend.read_file(str(resolved))
            lines = raw.content.split("\n")
            total_lines = len(lines)
            limits = ReadLimits()
            start = max(0, offset - 1) if offset > 0 else 0
            end = min(start + limit if limit else total_lines, start + limits.max_lines)
            selected = lines[start:end]
            numbered = [f"{start + i + 1:>6}\t{line}" for i, line in enumerate(selected)]
            content = "\n".join(numbered)
            self._update_file_tracking(
                resolved,
                is_partial=start > 0 or end < total_lines,
            )
            return content
        except Exception as e:
            return f"Error reading file: {e}"

    def _write_file(self, file_path: str, content: str) -> str:
        is_valid, error, resolved = self._validate_path(file_path, "write")
        if not is_valid:
            return error
        assert resolved is not None

        try:
            normalized = self._normalize_write_content(content)
            result = self.backend.write_file(str(resolved), normalized)
            if not result.success:
                return f"Error writing file: {result.error}"

            self._update_file_tracking(resolved, is_partial=False)
            self._record_operation(
                operation_type="write",
                file_path=file_path,
                before_content=None,
                after_content=normalized,
            )

            lines = normalized.count("\n") + 1
            return f"File created: {file_path}\n   Lines: {lines}\n   Size: {len(content)} bytes"
        except Exception as e:
            return f"Error writing file: {e}"

    def _edit_file(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        error, resolved = self._edit_preflight(file_path=file_path)
        if error is not None:
            return self._validation_message(error)
        assert resolved is not None

        try:
            # @@@edit-critical-lock
            # dt-01 requires the reread -> stale check -> write path to be one
            # synchronous critical section so two stale concurrent edits cannot
            # both commit from the same prior read snapshot.
            with self._edit_critical_section:
                try:
                    raw = self.backend.read_file(str(resolved))
                except FileNotFoundError:
                    if old_string == "":
                        return self._write_file(file_path, new_string)
                    return f"File not found: {file_path}"
                content = raw.content

                if old_string == "":
                    return "Cannot use empty old_string on an existing file. Use Write to replace the full file content."
                staleness_error = self._check_file_staleness(resolved)
                if staleness_error:
                    return staleness_error

                if old_string == new_string:
                    return "Error: old_string and new_string are identical (no-op edit)"

                # @@@edit-critical-staleness
                # te-06 needs a second stale-read check inside the read->write
                # critical section so an external write that lands after the
                # preflight check cannot be silently overwritten.
                staleness_error = self._check_file_staleness(resolved)
                if staleness_error:
                    return staleness_error

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

                self._update_file_tracking(resolved, is_partial=False)
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

    def _list_dir(self, path: str) -> str:
        directory_path = path
        error, resolved = self._list_dir_preflight(path=directory_path)
        if error is not None:
            return self._validation_message(error)
        assert resolved is not None

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
