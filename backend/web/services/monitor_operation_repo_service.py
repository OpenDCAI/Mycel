"""Monitor operation storage boundary."""

from __future__ import annotations

import copy
from threading import Lock
from typing import Any, Protocol


class MonitorOperationRepo(Protocol):
    def create(self, operation: dict[str, Any]) -> dict[str, Any]: ...

    def save(self, operation: dict[str, Any]) -> None: ...

    def list_for_target(self, target_type: str, target_id: str) -> list[dict[str, Any]]: ...

    def get(self, operation_id: str) -> dict[str, Any] | None: ...

    def clear(self) -> None: ...


class InMemoryMonitorOperationRepo:
    def __init__(self) -> None:
        self._lock = Lock()
        self._operations: dict[str, dict[str, Any]] = {}
        self._target_index: dict[tuple[str, str], list[str]] = {}

    def create(self, operation: dict[str, Any]) -> dict[str, Any]:
        operation_id = str(operation["operation_id"])
        target_key = (str(operation["target_type"]), str(operation["target_id"]))
        with self._lock:
            self._operations[operation_id] = operation
            self._target_index.setdefault(target_key, []).insert(0, operation_id)
        return operation

    def save(self, operation: dict[str, Any]) -> None:
        operation_id = str(operation["operation_id"])
        with self._lock:
            self._operations[operation_id] = operation

    def list_for_target(self, target_type: str, target_id: str) -> list[dict[str, Any]]:
        target_key = (target_type, target_id)
        with self._lock:
            ids = list(self._target_index.get(target_key, []))
            return [copy.deepcopy(self._operations[operation_id]) for operation_id in ids if operation_id in self._operations]

    def get(self, operation_id: str) -> dict[str, Any] | None:
        with self._lock:
            operation = self._operations.get(operation_id)
            return copy.deepcopy(operation) if operation is not None else None

    def clear(self) -> None:
        with self._lock:
            self._operations.clear()
            self._target_index.clear()


_DEFAULT_REPO: MonitorOperationRepo = InMemoryMonitorOperationRepo()


def default_monitor_operation_repo() -> MonitorOperationRepo:
    return _DEFAULT_REPO
