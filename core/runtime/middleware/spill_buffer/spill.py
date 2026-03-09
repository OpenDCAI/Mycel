"""Core spill logic: detect oversized content, write to disk, return preview."""

from __future__ import annotations

import os
from typing import Any

from core.tools.filesystem.backend import FileSystemBackend

PREVIEW_BYTES = 2048


def spill_if_needed(
    content: Any,
    threshold_bytes: int,
    tool_call_id: str,
    fs_backend: FileSystemBackend,
    workspace_root: str,
) -> Any:
    """Replace oversized string content with a preview + on-disk path.

    Args:
        content: Tool output (only strings are checked).
        threshold_bytes: Max byte size before spilling.
        tool_call_id: Used to derive the spill filename.
        fs_backend: Backend for writing the full output to disk.
        workspace_root: Root directory for the .leon/tool-results/ folder.

    Returns:
        Original content if within threshold, otherwise a preview string.
    """
    if not isinstance(content, str):
        return content

    size = len(content.encode("utf-8"))
    if size <= threshold_bytes:
        return content

    spill_dir = os.path.join(workspace_root, ".leon", "tool-results")
    spill_path = os.path.join(spill_dir, f"{tool_call_id}.txt")

    write_note = ""
    try:
        result = fs_backend.write_file(spill_path, content)
        if hasattr(result, "success") and not result.success:
            error_msg = getattr(result, "error", "unknown error")
            write_note = f"\n\n(Warning: failed to save full output to disk: {error_msg})"
            spill_path = "<write failed>"
    except Exception as exc:
        write_note = f"\n\n(Warning: failed to save full output to disk: {exc})"
        spill_path = "<write failed>"

    preview = content[:PREVIEW_BYTES]
    return (
        f"Output too large ({size} bytes). Full output saved to: {spill_path}"
        f"\n\nUse read_file to view specific sections with offset and limit parameters."
        f"\n\nPreview (first {PREVIEW_BYTES} bytes):\n{preview}\n..."
        f"{write_note}"
    )
