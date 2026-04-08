"""Base executor class and result types for command execution."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecuteResult:
    """Result of command execution."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    command_id: str | None = None

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def output(self) -> str:
        """Combined output (stdout + stderr if present)."""
        if self.stderr:
            return f"{self.stdout}\n[stderr]\n{self.stderr}".strip()
        return self.stdout.strip()

    def to_tool_result(self) -> str:
        """Format result for tool response."""
        if self.timed_out:
            return f"Command timed out.\n{self.output}"
        if self.exit_code != 0:
            return f"Exit code: {self.exit_code}\n{self.output}"
        return self.output or "(no output)"


@dataclass
class AsyncCommand:
    """Represents a running async command."""

    command_id: str
    command_line: str
    cwd: str
    process: Any = None
    stdout_buffer: list[str] = field(default_factory=list)
    stderr_buffer: list[str] = field(default_factory=list)
    exit_code: int | None = None
    done: bool = False
    cancelled: bool = False


class BaseExecutor(ABC):
    """Base class for shell executors."""

    shell_name: str = "unknown"
    shell_command: tuple[str, ...] = ()
    is_remote: bool = False
    runtime_owns_cwd: bool = False

    def __init__(self, default_cwd: str | None = None):
        self.default_cwd = default_cwd

    @abstractmethod
    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        """
        Execute a command and wait for completion.

        Args:
            command: Command to execute
            cwd: Working directory (uses default if not specified)
            timeout: Timeout in seconds (None = no timeout)
            env: Environment variables to set

        Returns:
            ExecuteResult with exit code, stdout, stderr
        """
        ...

    @abstractmethod
    async def execute_async(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncCommand:
        """
        Start a command without waiting for completion.

        Args:
            command: Command to execute
            cwd: Working directory
            env: Environment variables

        Returns:
            AsyncCommand with command_id for status queries
        """
        ...

    @abstractmethod
    async def get_status(self, command_id: str) -> AsyncCommand | None:
        """
        Get status of an async command.

        Args:
            command_id: ID returned by execute_async

        Returns:
            AsyncCommand with current status, or None if not found
        """
        ...

    @abstractmethod
    async def wait_for(
        self,
        command_id: str,
        timeout: float | None = None,
    ) -> ExecuteResult | None:
        """
        Wait for an async command to complete.

        Args:
            command_id: ID returned by execute_async
            timeout: Max seconds to wait

        Returns:
            ExecuteResult if command finished, None if not found
        """
        ...

    @abstractmethod
    def store_completed_result(
        self,
        command_id: str,
        command_line: str,
        cwd: str,
        result: ExecuteResult,
    ) -> None:
        """
        Store a completed command result for later retrieval via command_status.

        Used when blocking mode output is truncated, allowing user to read
        the full output using command_status with offset/limit.

        Args:
            command_id: Unique ID for this result
            command_line: The command that was executed
            cwd: Working directory used
            result: The execution result to store
        """
        ...
