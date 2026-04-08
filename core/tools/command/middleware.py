"""Command Middleware - shell command execution.

Provides run_command and command_status tools.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Literal

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain.tools import ToolRuntime, tool
from langgraph.runtime import Runtime

from sandbox.shell_output import normalize_pty_result

from .base import AsyncCommand, BaseExecutor, describe_execution_exception
from .dispatcher import get_executor, get_shell_info

logger = logging.getLogger(__name__)

RUN_COMMAND_TOOL_NAME = "run_command"
COMMAND_STATUS_TOOL_NAME = "command_status"

DEFAULT_TIMEOUT = 120.0
DEFAULT_WAIT_MS_BEFORE_ASYNC = 500


class CommandState(AgentState):
    """State for command middleware."""

    pass


class CommandMiddleware(AgentMiddleware[CommandState]):
    """
    Command execution middleware.

    Features:
    - run_command tool with CommandLine, Cwd, Blocking, Timeout params
    - command_status tool for async command queries
    - Extensible hook system for security checks
    - Auto-detects shell based on OS (zsh/bash/powershell)
    """

    state_schema = CommandState

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        default_timeout: float = DEFAULT_TIMEOUT,
        hooks: list[Any] | None = None,
        env: dict[str, str] | None = None,
        enabled_tools: dict[str, bool] | None = None,
        executor: BaseExecutor | None = None,
        registry: Any = None,
        queue_manager: Any = None,
        verbose: bool = True,
    ) -> None:
        """
        Initialize CommandMiddleware.

        Args:
            workspace_root: Default working directory for commands
            default_timeout: Default timeout in seconds for blocking commands
            hooks: List of hook instances for command validation
            env: Additional environment variables
            executor: External executor (default: auto-detect OS shell)
            registry: BackgroundTaskRegistry for task state management
            queue_manager: MessageQueueManager for notification injection
            verbose: Whether to output detailed logs
        """
        AgentMiddleware.__init__(self)
        self._agent: Any = None
        self._registry = registry
        self._queue_manager = queue_manager

        # @@@ Don't resolve workspace_root for sandbox — macOS firmlinks break it
        if executor is not None and executor.is_remote:
            self.workspace_root = Path(workspace_root)
        else:
            self.workspace_root = Path(workspace_root).resolve()
        self.default_timeout = default_timeout
        self.hooks = hooks or []
        self.env = env
        self.enabled_tools = enabled_tools or {"run_command": True, "command_status": True}
        self.verbose = verbose

        # Use provided executor or auto-detect
        if executor is not None:
            self._executor = executor
        else:
            self._executor = get_executor(default_cwd=str(self.workspace_root))

        if self.verbose:
            executor_name = type(self._executor).__name__
            if hasattr(self._executor, "shell_name"):
                shell_label = self._executor.shell_name
            else:
                shell_info = get_shell_info()
                shell_label = shell_info["shell_name"]
            print(f"[Command] Initialized: {shell_label} (executor: {executor_name})")
            print(f"[Command] Workspace: {self.workspace_root}")
            print(f"[Command] Loaded {len(self.hooks)} hooks")

        @tool(RUN_COMMAND_TOOL_NAME)
        async def run_command_tool(
            *,
            runtime: ToolRuntime[CommandState],
            CommandLine: str,
            Cwd: str | None = None,
            Blocking: bool = True,
            Timeout: int | None = None,
        ) -> str:
            """Execute shell command. OS auto-detects shell (mac→zsh, linux→bash, win→powershell).

            Args:
                CommandLine: Command to execute
                Cwd: Working directory (optional, defaults to workspace root)
                Blocking: Wait for completion (default: true). If false, returns CommandId for status queries.
                Timeout: Timeout in seconds (optional, default: 120)
            """
            return await self._execute_command(
                command_line=CommandLine,
                cwd=Cwd,
                blocking=Blocking,
                timeout=Timeout,
            )

        @tool(COMMAND_STATUS_TOOL_NAME)
        async def command_status_tool(
            *,
            runtime: ToolRuntime[CommandState],
            CommandId: str,
            WaitDurationSeconds: int = 0,
        ) -> str:
            """Check status of a non-blocking command.

            Args:
                CommandId: ID returned by run_command with Blocking=false
                WaitDurationSeconds: Seconds to wait for completion (0 = immediate check)
            """
            return await self._get_command_status(
                command_id=CommandId,
                wait_seconds=WaitDurationSeconds,
            )

        self._run_command_tool = run_command_tool
        self._command_status_tool = command_status_tool
        self.tools = [self._run_command_tool, self._command_status_tool]

    def _check_hooks(self, command: str) -> tuple[bool, str]:
        """Run command through all hooks. Returns (allowed, error_message)."""
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

    async def _execute_command(
        self,
        command_line: str,
        cwd: str | None,
        blocking: bool,
        timeout: int | None,
    ) -> str:
        """Execute command with hook validation."""
        allowed, error_msg = self._check_hooks(command_line)
        if not allowed:
            return error_msg

        # @@@runtime-owned-cwd - Stateful runtimes (remote/local chat session shells) own cwd continuity.
        work_dir = cwd if self._executor.runtime_owns_cwd else (cwd or str(self.workspace_root))

        if blocking:
            return await self._execute_blocking(command_line, work_dir, timeout)
        else:
            return await self._execute_async(command_line, work_dir, timeout)

    async def _execute_blocking(self, command_line: str, work_dir: str | None, timeout: int | None) -> str:
        """Execute blocking command. SpillBuffer middleware handles oversized output."""
        timeout_secs = float(timeout) if timeout else self.default_timeout
        try:
            result = await self._executor.execute(
                command=command_line,
                cwd=work_dir,
                timeout=timeout_secs,
                env=self.env,
            )
        except Exception as e:
            return f"Error executing command: {describe_execution_exception(e)}"
        return result.to_tool_result()

    def set_agent(self, agent: Any) -> None:
        """Set parent agent for runtime access."""
        self._agent = agent

    async def _execute_async(self, command_line: str, work_dir: str | None, timeout: int | None) -> str:
        """Execute async command."""
        try:
            async_cmd = await self._executor.execute_async(
                command=command_line,
                cwd=work_dir,
                env=self.env,
            )
        except Exception as e:
            return f"Error starting async command: {describe_execution_exception(e)}"

        # Emit task_start event
        runtime = getattr(self._agent, "runtime", None) if self._agent else None
        if runtime:
            runtime.emit_activity_event(
                {
                    "event": "task_start",
                    "data": json.dumps(
                        {
                            "task_id": async_cmd.command_id,
                            "task_type": "bash",
                            "command_line": command_line,
                            "background": True,
                        },
                        ensure_ascii=False,
                    ),
                }
            )

        if timeout and timeout > 0:
            await asyncio.sleep(min(timeout, 1.0))

        try:
            status = await self._executor.get_status(async_cmd.command_id)
            if status and status.done:
                result = await self._executor.wait_for(async_cmd.command_id)
                if result:
                    return result.to_tool_result()
        except (TimeoutError, OSError) as e:
            logger.debug("Status check failed for %s (command may still be running): %s", async_cmd.command_id, e)
        except Exception:
            logger.warning("Unexpected error checking status for command %s", async_cmd.command_id, exc_info=True)

        # Start background monitoring
        if runtime:
            asyncio.create_task(self._monitor_async_command(async_cmd.command_id, command_line, runtime))

        return f"Command started in background.\nCommandId: {async_cmd.command_id}\nUse command_status tool to check progress."

    async def _monitor_async_command(self, command_id: str, command_line: str, runtime: Any) -> None:
        """Monitor async command and emit completion events."""
        while True:
            await asyncio.sleep(2.0)
            try:
                status = await self._executor.get_status(command_id)
            except Exception:
                logger.debug("Failed to get status for command %s", command_id)
                break
            if status is None:
                break

            if status.done:
                # Get final output
                output = self._merge_running_output(status)
                exit_code = status.exit_code or 0
                if getattr(status, "cancelled", False):
                    task_status = "cancelled"
                else:
                    task_status = "completed" if exit_code == 0 else "failed"

                # Update registry first
                if self._registry:
                    try:
                        await self._registry.update(
                            command_id,
                            status=task_status,
                            exit_code=exit_code,
                            stdout_buffer=[output],
                        )
                    except Exception as e:
                        logger.warning("Failed to update registry for command %s: %s", command_id, e)

                # Inject CommandNotification to queue
                if self._queue_manager:
                    await self._inject_command_notification(
                        command_id=command_id,
                        status=task_status,
                        exit_code=exit_code,
                        command_line=command_line,
                        output=output,
                    )

                # Emit task completion event
                if getattr(status, "cancelled", False):
                    event_type = "task_done"
                else:
                    event_type = "task_done" if exit_code == 0 else "task_error"
                runtime.emit_activity_event(
                    {
                        "event": event_type,
                        "data": json.dumps(
                            {
                                "task_id": command_id,
                                "exit_code": exit_code,
                                "background": True,
                                "cancelled": bool(getattr(status, "cancelled", False)),
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
                break

    async def _inject_command_notification(
        self,
        command_id: str,
        status: Literal["completed", "failed"],
        exit_code: int,
        command_line: str,
        output: str,
    ) -> None:
        """Inject CommandNotification to unified queue."""
        from core.runtime.middleware.queue.formatters import format_command_notification
        from sandbox.thread_context import get_current_thread_id

        notification = format_command_notification(
            command_id=command_id,
            status=status,
            exit_code=exit_code,
            command_line=command_line,
            output=output,
        )

        # Inject to queue (wake idle agent)
        thread_id = get_current_thread_id()
        if thread_id:
            self._queue_manager.enqueue(notification, thread_id, notification_type="command")

    def _clean_running_output(self, output: str, command_line: str) -> str:
        return normalize_pty_result(output, command_line)

    @staticmethod
    def _merge_running_output(status: AsyncCommand) -> str:
        stdout = "".join(status.stdout_buffer)
        stderr = "".join(status.stderr_buffer)
        if stdout and stderr:
            return f"{stdout}\n{stderr}".strip()
        return (stdout or stderr).strip()

    async def _get_command_status(
        self,
        command_id: str,
        wait_seconds: int,
    ) -> str:
        """Get status of async command."""
        try:
            return await self._get_command_status_inner(command_id, wait_seconds)
        except (RuntimeError, OSError) as e:
            return f"Error: {e}"

    async def _get_command_status_inner(
        self,
        command_id: str,
        wait_seconds: int,
    ) -> str:
        if wait_seconds > 0:
            result = await self._executor.wait_for(command_id, timeout=float(min(wait_seconds, 60)))
            if result:
                # @@@status-timeout-semantics - wait timeout means command is still running, not done.
                if result.timed_out:
                    status = await self._executor.get_status(command_id)
                    if status is None:
                        return f"Error: Command {command_id} not found"
                    combined_output = self._merge_running_output(status)
                    cleaned_output = self._clean_running_output(combined_output, status.command_line)
                    return f"Status: running\nCommand: {status.command_line}\nOutput so far:\n{cleaned_output}"
                output = result.to_tool_result()
                terminal = "cancelled" if getattr(result, "cancelled", False) else "done"
                return f"Status: {terminal}\nExit code: {result.exit_code}\n{output}"

        status = await self._executor.get_status(command_id)
        if status is None:
            return f"Error: Command {command_id} not found"

        if status.done:
            result = await self._executor.wait_for(command_id)
            if result:
                output = result.to_tool_result()
                terminal = "cancelled" if getattr(status, "cancelled", False) else "done"
                return f"Status: {terminal}\nExit code: {result.exit_code}\n{output}"

        combined_output = self._merge_running_output(status)
        cleaned_output = self._clean_running_output(combined_output, status.command_line)
        return f"Status: running\nCommand: {status.command_line}\nOutput so far:\n{cleaned_output}"

    def before_agent(self, state: CommandState, runtime: Runtime) -> dict[str, Any] | None:
        return None

    async def abefore_agent(self, state: CommandState, runtime: Runtime) -> dict[str, Any] | None:
        return None

    def after_agent(self, state: CommandState, runtime: Runtime) -> None:
        pass

    async def aafter_agent(self, state: CommandState, runtime: Runtime) -> None:
        pass

    def wrap_model_call(self, request: ModelRequest, handler) -> ModelResponse:
        return handler(request)

    async def awrap_model_call(self, request: ModelRequest, handler) -> ModelResponse:
        return await handler(request)

    def wrap_tool_call(self, request, handler):
        return handler(request)

    async def awrap_tool_call(self, request, handler):
        return await handler(request)


__all__ = ["CommandMiddleware"]
