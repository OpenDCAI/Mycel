"""Text file reader with triple limits: lines, chars, line length."""

from __future__ import annotations

from pathlib import Path

from core.tools.filesystem.read.types import FileType, ReadLimits, ReadResult


def read_text(
    path: Path,
    limits: ReadLimits,
    offset: int | None = None,
    limit: int | None = None,
) -> ReadResult:
    """
    Read text file with triple limits.

    Limits applied (first reached wins):
    1. max_lines: Maximum number of lines to return
    2. max_chars: Maximum total characters to return
    3. max_line_length: Truncate individual lines exceeding this

    Args:
        path: Absolute path to file
        limits: ReadLimits configuration
        offset: Start line (1-indexed, None = start from beginning)
        limit: Number of lines to read (None = use limits.max_lines)

    Returns:
        ReadResult with content and metadata
    """
    result = ReadResult(
        file_path=str(path),
        file_type=FileType.TEXT,
        total_size=path.stat().st_size,
    )

    try:
        with open(path, encoding="utf-8") as f:
            all_lines = f.readlines()
    except UnicodeDecodeError:
        result.error = f"Cannot read file (not UTF-8): {path}"
        return result
    except Exception as e:
        result.error = f"Error reading file: {e}"
        return result

    total_lines = len(all_lines)
    result.total_lines = total_lines

    start_idx = (offset - 1) if offset and offset > 0 else 0
    if start_idx >= total_lines:
        result.error = f"Offset {offset} exceeds file length {total_lines}"
        return result

    effective_limit = limit or limits.max_lines
    if offset is None and limit is None and total_lines > limits.max_lines:
        effective_limit = limits.max_lines

    lines_to_process = all_lines[start_idx:]

    output_lines: list[str] = []
    total_chars = 0
    truncated = False
    truncation_reason: str | None = None
    line_count = 0

    for i, line in enumerate(lines_to_process):
        if line_count >= effective_limit:
            truncated = True
            truncation_reason = f"max_lines={effective_limit}"
            break

        line_stripped = line.rstrip("\n\r")

        if len(line_stripped) > limits.max_line_length:
            line_stripped = line_stripped[: limits.max_line_length] + "... [truncated]"

        line_with_number = f"{start_idx + i + 1:6d}→{line_stripped}"

        if total_chars + len(line_with_number) > limits.max_chars:
            truncated = True
            truncation_reason = f"max_chars={limits.max_chars}"
            break

        output_lines.append(line_with_number)
        total_chars += len(line_with_number) + 1
        line_count += 1

    result.content = "\n".join(output_lines)
    result.start_line = start_idx + 1
    result.end_line = start_idx + line_count
    result.truncated = truncated
    result.truncation_reason = truncation_reason

    return result
