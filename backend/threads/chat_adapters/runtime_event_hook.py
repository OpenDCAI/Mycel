from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Iterable
from typing import Any

from backend.threads.chat_adapters.runtime_event_runner import run_planned_runtime_event


def make_sync_runtime_event_hook[**P](async_fn: Callable[P, Coroutine[Any, Any, Any]]) -> Callable[P, None]:
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


def make_planned_runtime_event_hook[EventT, ActionT](
    planner: Callable[[EventT], Iterable[ActionT]],
    dispatch_actions: Callable[[list[ActionT]], Coroutine[Any, Any, Any]],
) -> Callable[[EventT], None]:
    async def dispatch_event(event: EventT) -> None:
        await run_planned_runtime_event(event, planner, dispatch_actions)

    return make_sync_runtime_event_hook(dispatch_event)
