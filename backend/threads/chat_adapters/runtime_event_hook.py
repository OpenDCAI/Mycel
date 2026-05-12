from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any


def make_sync_runtime_event_hook[**P](async_fn: Callable[P, Coroutine[Any, Any, None]]) -> Callable[P, None]:
    loop = asyncio.get_running_loop()

    def hook(*args: P.args, **kwargs: P.kwargs) -> None:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is loop:
            raise RuntimeError("Sync runtime event hook cannot run on its owner event loop thread")
        future = asyncio.run_coroutine_threadsafe(async_fn(*args, **kwargs), loop)
        future.result()

    return hook
