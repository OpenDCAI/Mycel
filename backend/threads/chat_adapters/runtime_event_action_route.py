from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from typing import Any


def _make_sync_runtime_event_hook[**P](async_fn: Callable[P, Coroutine[Any, Any, Any]]) -> Callable[P, None]:
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


@dataclass(frozen=True)
class RuntimeEventActionRoute[EventT, ActionT, ResultT]:
    planner: Callable[[EventT], Iterable[ActionT]]
    dispatch_actions: Callable[[list[ActionT]], Coroutine[Any, Any, ResultT]]

    async def dispatch(self, event: EventT) -> ResultT:
        actions = list(self.planner(event))
        return await self.dispatch_actions(actions)

    def sync_hook(self) -> Callable[[EventT], None]:
        async def dispatch_event(event: EventT) -> None:
            await self.dispatch(event)

        return _make_sync_runtime_event_hook(dispatch_event)
