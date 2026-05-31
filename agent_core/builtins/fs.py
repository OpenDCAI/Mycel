"""Workspace-contained filesystem tools."""

from __future__ import annotations

from pathlib import Path

from agent_core.registry import ToolEntry, ToolMode, make_tool_schema


def _resolve(root: Path, path: str) -> Path:
    """Resolve ``path`` under ``root``, rejecting anything that escapes it."""
    root = root.resolve()
    candidate = (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"path escapes workspace: {path!r}")
    return candidate


def filesystem_tools(root: Path) -> list[ToolEntry]:
    def read_file(path: str) -> str:
        p = _resolve(root, path)
        if not p.is_file():
            return f"<error>not a file: {path}</error>"
        return p.read_text(encoding="utf-8", errors="replace")

    def write_file(path: str, content: str) -> str:
        p = _resolve(root, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} chars to {path}"

    def list_dir(path: str = ".") -> str:
        p = _resolve(root, path)
        if not p.is_dir():
            return f"<error>not a directory: {path}</error>"
        names = sorted(c.name + ("/" if c.is_dir() else "") for c in p.iterdir())
        return "\n".join(names) if names else "(empty)"

    return [
        ToolEntry(
            name="read_file",
            mode=ToolMode.INLINE,
            schema=make_tool_schema(
                name="read_file",
                description="Read a UTF-8 text file from the workspace.",
                properties={"path": {"type": "string"}},
                required=["path"],
            ),
            handler=read_file,
            source="builtin",
            search_hint="read file contents",
            is_read_only=True,
            is_concurrency_safe=True,
        ),
        ToolEntry(
            name="write_file",
            mode=ToolMode.INLINE,
            schema=make_tool_schema(
                name="write_file",
                description="Write (overwrite) a UTF-8 text file in the workspace, creating parents.",
                properties={"path": {"type": "string"}, "content": {"type": "string"}},
                required=["path", "content"],
            ),
            handler=write_file,
            source="builtin",
            search_hint="write create file",
            is_destructive=True,
        ),
        ToolEntry(
            name="list_dir",
            mode=ToolMode.INLINE,
            schema=make_tool_schema(
                name="list_dir",
                description="List entries of a directory in the workspace.",
                properties={"path": {"type": "string"}},
            ),
            handler=list_dir,
            source="builtin",
            search_hint="list directory entries",
            is_read_only=True,
            is_concurrency_safe=True,
        ),
    ]
