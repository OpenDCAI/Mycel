from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any


def make_blocking_runtime_event_hook[EventT](
    dispatch_event: Callable[[EventT], Coroutine[Any, Any, Any]],
) -> Callable[[EventT], None]:
    loop = asyncio.get_running_loop()

    def hook(event: EventT) -> None:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is loop:
            raise RuntimeError("Blocking runtime event hook cannot run on its owner event loop thread")
        future = asyncio.run_coroutine_threadsafe(dispatch_event(event), loop)
        future.result()

    return hook
