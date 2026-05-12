from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


def run_sync_actions(
    actions: Iterable[Callable[..., None]],
    /,
    *args: Any,
    on_error: Callable[[Exception], Exception],
) -> None:
    current_actions = list(actions)
    if not current_actions:
        return
    try:
        for action in current_actions:
            action(*args)
    except Exception as exc:
        raise on_error(exc) from exc
