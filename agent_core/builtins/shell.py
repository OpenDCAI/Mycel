"""A minimal local bash tool (runs in the workspace dir).

Standalone default. For sandboxed/remote execution, supply a tool backed by an
``executor`` port adapter instead.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_core.registry import ToolEntry, ToolMode, make_tool_schema


def shell_tools(root: Path) -> list[ToolEntry]:
    def run_bash(command: str, timeout: int = 30) -> str:
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"<error>command timed out after {timeout}s</error>"
        out = proc.stdout or ""
        err = proc.stderr or ""
        parts = []
        if out:
            parts.append(out.rstrip())
        if err:
            parts.append(f"[stderr]\n{err.rstrip()}")
        parts.append(f"[exit {proc.returncode}]")
        return "\n".join(parts)

    return [
        ToolEntry(
            name="run_bash",
            mode=ToolMode.INLINE,
            schema=make_tool_schema(
                name="run_bash",
                description="Run a bash command in the workspace directory and return stdout/stderr/exit code.",
                properties={
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 600},
                },
                required=["command"],
            ),
            handler=run_bash,
            source="builtin",
            search_hint="run shell bash command",
            is_destructive=True,
        ),
    ]
