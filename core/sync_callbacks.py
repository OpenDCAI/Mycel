from __future__ import annotations

from collections.abc import Callable
from typing import Any


class SyncActionRegistry:
    def __init__(self) -> None:
        self._actions: list[Callable[..., None]] = []

    def add(self, action: Callable[..., None]) -> None:
        self._actions.append(action)

    def has_actions(self) -> bool:
        return bool(self._actions)

    def run(
        self,
        /,
        *args: Any,
        on_error: Callable[[Exception], Exception],
    ) -> None:
        current_actions = list(self._actions)
        if not current_actions:
            return
        try:
            for action in current_actions:
                action(*args)
        except Exception as exc:
            raise on_error(exc) from exc
