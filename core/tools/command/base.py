"""Base executor class and result types for command execution.

Canonical location: sandbox.interfaces.executor
This module re-exports for backward compatibility.
"""

from sandbox.interfaces.executor import *  # noqa: F401,F403
from sandbox.interfaces.executor import AsyncCommand, BaseExecutor, ExecuteResult

__all__ = ["BaseExecutor", "ExecuteResult", "AsyncCommand"]
