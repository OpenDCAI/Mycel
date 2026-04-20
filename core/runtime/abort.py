"""Minimal abort controller tree for runtime lifecycle wiring."""

from __future__ import annotations

from collections.abc import Callable


class AbortController:
    def __init__(self) -> None:
        self._aborted = False
        self._listeners: dict[int, Callable[[], None]] = {}
        self._next_listener_id = 0

    def abort(self) -> None:
        if self._aborted:
            return
        self._aborted = True
        listeners = list(self._listeners.values())
        self._listeners.clear()
        for listener in listeners:
            listener()

    def is_aborted(self) -> bool:
        return self._aborted

    def on_abort(self, listener: Callable[[], None]) -> Callable[[], None]:
        if self._aborted:
            listener()
            return lambda: None

        listener_id = self._next_listener_id
        self._next_listener_id += 1
        self._listeners[listener_id] = listener

        def unsubscribe() -> None:
            self._listeners.pop(listener_id, None)

        return unsubscribe


def create_child_abort_controller(parent: AbortController | None) -> AbortController:
    child = AbortController()
    if parent is None:
        return child

    unsubscribe = parent.on_abort(child.abort)
    child.on_abort(unsubscribe)
    return child
