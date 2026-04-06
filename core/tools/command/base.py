"""Base executor class and result types for command execution.

Canonical location: sandbox.interfaces.executor
This module re-exports for backward compatibility.
"""

from __future__ import annotations

from sandbox.interfaces.executor import *  # noqa: F401,F403
from sandbox.interfaces.executor import AsyncCommand, BaseExecutor, ExecuteResult

__all__ = ["BaseExecutor", "ExecuteResult", "AsyncCommand"]


def describe_execution_exception(exc: Exception) -> str:
    detail = str(exc).strip()
    if detail:
        return detail
    return exc.__class__.__name__


def require_subprocess_pipe[TPipe](pipe: TPipe | None, name: str) -> TPipe:
    # @@@persistent-shell-pipe-contract - persistent shell executors only work
    # when asyncio created real stdio pipes; fail loudly instead of pretending
    # optional streams are always present.
    if pipe is None:
        raise RuntimeError(f"Subprocess missing {name} pipe")
    return pipe
