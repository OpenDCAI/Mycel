"""A small, dependency-free builtin toolset for standalone agents.

These are deliberately minimal (workspace-contained fs + bash). Richer tools
(search, LSP, web, MCP) can be lifted from Mycel's ``core/tools`` later; they all
register the same ``ToolEntry`` shape.
"""

from __future__ import annotations

from pathlib import Path

from agent_core.builtins.fs import filesystem_tools
from agent_core.builtins.shell import shell_tools
from agent_core.registry import ToolEntry


def default_toolset(workspace_root: str | Path) -> list[ToolEntry]:
    root = Path(workspace_root)
    return [*filesystem_tools(root), *shell_tools(root)]


__all__ = ["default_toolset", "filesystem_tools", "shell_tools"]
