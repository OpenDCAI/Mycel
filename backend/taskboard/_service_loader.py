"""Typed task_service loader for taskboard surfaces."""

from __future__ import annotations

from typing import Any, Protocol, cast


class TaskServiceProtocol(Protocol):
    def list_tasks(self) -> list[dict[str, Any]]: ...
    def get_task(self, task_id: str) -> dict[str, Any] | None: ...
    def get_highest_priority_pending_task(self) -> dict[str, Any] | None: ...
    def create_task(self, **fields: Any) -> dict[str, Any]: ...
    def update_task(self, task_id: str, **fields: Any) -> dict[str, Any] | None: ...


try:
    from backend.web.services import task_service as _task_service
except ImportError:
    _task_service = None


def require_task_service() -> TaskServiceProtocol:
    if _task_service is None:
        raise RuntimeError("backend.web.services.task_service is unavailable")
    return cast(TaskServiceProtocol, _task_service)
