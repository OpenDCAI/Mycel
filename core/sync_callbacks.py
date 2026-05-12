from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


def run_sync_callbacks(
    callbacks: Iterable[Callable[..., None]],
    /,
    *args: Any,
    on_error: Callable[[Exception], Exception],
) -> None:
    current_callbacks = list(callbacks)
    if not current_callbacks:
        return
    try:
        for callback in current_callbacks:
            callback(*args)
    except Exception as exc:
        raise on_error(exc) from exc
