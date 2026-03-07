"""Command Service - registers Bash tool with ToolRegistry.

Tools:
- Bash: Execute shell commands (parameter names aligned to CC)

Parameter mapping from old run_command:
- CommandLine -> command
- Blocking -> run_in_background (semantics inverted)
- Timeout (seconds) -> timeout (milliseconds, default 120000)
- Cwd -> removed
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from sandbox.shell_output import normalize_pty_result

from core.tools.command.base import AsyncCommand, BaseExecutor
from core.tools.command.dispatcher import get_executor

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 120_000


class CommandService:
    """Registers Bash tool into ToolRegistry."""

    def __init__(
        self,
        registry: ToolRegistry,
        workspace_root: str | Path,
        *,
        hooks: list[Any] | None = None,
        env: dict[str, str] | None = None,
        executor: BaseExecutor | None = None,
        queue_manager: Any = None,
        background_runs: dict | None = None,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.hooks = hooks or []
        self.env = env
        self._queue_manager = queue_manager
        self._background_runs = background_runs  # shared with AgentService

        if executor is not None:
            self._executor = executor
            if executor.is_remote:
                self.workspace_root = Path(workspace_root)
        else:
            self._executor = get_executor(default_cwd=str(self.workspace_root))

        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        registry.register(ToolEntry(
            name="Bash",
            mode=ToolMode.INLINE,
            schema={
                "name": "Bash",
                "description": (
                    "Execute shell command. OS auto-detects shell "
                    "(mac->zsh, linux->bash, win->powershell)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Command to execute",
                        },
                        "run_in_background": {
                            "type": "boolean",
                            "description": "Run in background (default: false). Returns task ID for status queries.",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in milliseconds (default: 120000)",
                        },
                    },
                    "required": ["command"],
                },
            },
            handler=self._bash,
            source="CommandService",
        ))

    def _check_hooks(self, command: str) -> tuple[bool, str]:
        context = {"workspace_root": str(self.workspace_root)}
        for hook in self.hooks:
            if not hook.enabled:
                continue
            result = hook.check_command(command, context)
            if not result.allow:
                return False, result.error_message
            if not result.continue_chain:
                break
        return True, ""

    async def _bash(
        self,
        command: str,
        run_in_background: bool = False,
        timeout: int = DEFAULT_TIMEOUT_MS,
    ) -> str:
        allowed, error_msg = self._check_hooks(command)
        if not allowed:
            return error_msg

        work_dir = None if self._executor.runtime_owns_cwd else str(self.workspace_root)
        timeout_secs = timeout / 1000.0

        if not run_in_background:
            return await self._execute_blocking(command, work_dir, timeout_secs)
        else:
            return await self._execute_async(command, work_dir, timeout_secs)

    async def _execute_blocking(self, command: str, work_dir: str | None, timeout_secs: float) -> str:
        try:
            result = await self._executor.execute(
                command=command,
                cwd=work_dir,
                timeout=timeout_secs,
                env=self.env,
            )
        except Exception as e:
            return f"Error executing command: {e}"
        return result.to_tool_result()

    async def _execute_async(self, command: str, work_dir: str | None, timeout_secs: float) -> str:
        try:
            async_cmd = await self._executor.execute_async(
                command=command,
                cwd=work_dir,
                env=self.env,
            )
        except Exception as e:
            return f"Error starting async command: {e}"

        task_id = async_cmd.command_id

        if self._background_runs is not None:
            from core.agents.service import _BashBackgroundRun
            self._background_runs[task_id] = _BashBackgroundRun(async_cmd, command)

        return (
            f"Command started in background.\n"
            f"task_id: {task_id}\n"
            f"Use TaskOutput to get result."
        )
