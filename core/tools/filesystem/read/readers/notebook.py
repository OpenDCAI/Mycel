"""Jupyter Notebook reader - parses .ipynb cell by cell."""

from __future__ import annotations

import json
from pathlib import Path

from core.tools.filesystem.read.types import FileType, ReadLimits, ReadResult


def read_notebook(
    path: Path,
    limits: ReadLimits,
    start_cell: int | None = None,
    limit_cells: int | None = None,
) -> ReadResult:
    """
    Read Jupyter Notebook with cell-based pagination.

    Args:
        path: Absolute path to .ipynb file
        limits: ReadLimits configuration (max_chars applies to total output)
        start_cell: Start cell (0-indexed, None = start from cell 0)
        limit_cells: Number of cells to read (None = default 50 cells)

    Returns:
        ReadResult with formatted cells and metadata
    """
    stat = path.stat()
    result = ReadResult(
        file_path=str(path),
        file_type=FileType.NOTEBOOK,
        total_size=stat.st_size,
    )

    try:
        with open(path, encoding="utf-8") as f:
            notebook = json.load(f)
    except json.JSONDecodeError as e:
        result.error = f"Invalid notebook JSON: {e}"
        return result
    except Exception as e:
        result.error = f"Error reading notebook: {e}"
        return result

    cells = notebook.get("cells", [])
    total_cells = len(cells)
    result.total_cells = total_cells

    if total_cells == 0:
        result.content = "Empty notebook (no cells)"
        return result

    start_idx = start_cell if start_cell and start_cell >= 0 else 0
    if start_idx >= total_cells:
        result.error = f"Start cell {start_cell} exceeds total cells {total_cells}"
        return result

    effective_limit = limit_cells or 50
    end_idx = min(start_idx + effective_limit, total_cells)

    output_parts: list[str] = []
    total_chars = 0
    truncated = False
    truncation_reason: str | None = None
    cells_read = 0

    for cell_num in range(start_idx, end_idx):
        cell = cells[cell_num]
        cell_text = _format_cell(cell, cell_num, total_cells)

        if total_chars + len(cell_text) > limits.max_chars:
            truncated = True
            truncation_reason = f"max_chars={limits.max_chars}"
            remaining = limits.max_chars - total_chars
            if remaining > 100:
                output_parts.append(cell_text[:remaining] + "\n... [truncated]")
                cells_read += 1
            break

        output_parts.append(cell_text)
        total_chars += len(cell_text)
        cells_read += 1

    if end_idx < total_cells and not truncated:
        truncated = True
        truncation_reason = f"limit_cells={effective_limit}"

    result.content = "\n".join(output_parts)
    result.start_line = start_idx
    result.end_line = start_idx + cells_read - 1
    result.truncated = truncated
    result.truncation_reason = truncation_reason

    return result


def _format_cell(cell: dict, cell_num: int, total_cells: int) -> str:
    """Format a single notebook cell."""
    cell_type = cell.get("cell_type", "unknown")
    source = cell.get("source", [])

    if isinstance(source, list):
        source_text = "".join(source)
    else:
        source_text = str(source)

    parts = [
        f"\n{'─' * 60}",
        f"Cell [{cell_num}] ({cell_type}) | {cell_num + 1}/{total_cells}",
        "─" * 60,
    ]

    if cell_type == "code":
        parts.append(f"```python\n{source_text}\n```")

        outputs = cell.get("outputs", [])
        if outputs:
            parts.append("\n[Output]:")
            for output in outputs[:3]:
                output_text = _format_output(output)
                if output_text:
                    parts.append(output_text)
            if len(outputs) > 3:
                parts.append(f"... and {len(outputs) - 3} more outputs")

    elif cell_type == "markdown":
        parts.append(source_text)

    else:
        parts.append(f"[{cell_type}]\n{source_text}")

    return "\n".join(parts)


def _format_output(output: dict) -> str:
    """Format a cell output."""
    output_type = output.get("output_type", "")

    if output_type == "stream":
        text = output.get("text", [])
        if isinstance(text, list):
            text = "".join(text)
        return text[:500] + ("..." if len(text) > 500 else "")

    if output_type == "execute_result":
        data = output.get("data", {})
        if "text/plain" in data:
            text = data["text/plain"]
            if isinstance(text, list):
                text = "".join(text)
            return text[:500] + ("..." if len(text) > 500 else "")

    if output_type == "error":
        ename = output.get("ename", "Error")
        evalue = output.get("evalue", "")
        return f"[Error] {ename}: {evalue}"

    if output_type == "display_data":
        data = output.get("data", {})
        if "image/png" in data or "image/jpeg" in data:
            return "[Image output]"
        if "text/html" in data:
            return "[HTML output]"
        if "text/plain" in data:
            text = data["text/plain"]
            if isinstance(text, list):
                text = "".join(text)
            return text[:300] + ("..." if len(text) > 300 else "")

    return ""
