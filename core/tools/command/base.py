"""Base executor class and result types for command execution.

Canonical location: sandbox.interfaces.executor
This module re-exports for backward compatibility.
"""

from sandbox.interfaces.executor import *  # noqa: F401,F403
from sandbox.interfaces.executor import AsyncCommand, BaseExecutor, ExecuteResult

__all__ = ["BaseExecutor", "ExecuteResult", "AsyncCommand"]


def describe_execution_exception(exc: Exception) -> str:
    detail = str(exc).strip()
    if detail:
        return detail
    return exc.__class__.__name__
