"""Thread context tracking via ContextVar."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_current_thread_id: ContextVar[str] = ContextVar("sandbox_thread_id", default="")
# @@@run-context - groups file ops per execution unit: checkpoint_id in TUI, run_id in web mode.
_current_run_id: ContextVar[str] = ContextVar("sandbox_run_id", default="")
# Parent conversation messages — set by QueryLoop before tool execution; read by AgentService
# for forkContext=True sub-agent spawning.
_current_messages: ContextVar[list[Any]] = ContextVar("current_messages", default=[])


def set_current_thread_id(thread_id: str) -> None:
    _current_thread_id.set(thread_id)


def get_current_thread_id() -> str | None:
    value = _current_thread_id.get()
    return value if value else None


def set_current_run_id(run_id: str) -> None:
    _current_run_id.set(run_id)


def get_current_run_id() -> str | None:
    value = _current_run_id.get()
    return value if value else None


def set_current_messages(messages: list[Any]) -> None:
    _current_messages.set(list(messages))


def get_current_messages() -> list[Any]:
    return _current_messages.get()
