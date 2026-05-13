from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeEventActionRoute[EventT, ActionT, ResultT]:
    planner: Callable[[EventT], Iterable[ActionT]]
    dispatch_actions: Callable[[list[ActionT]], Coroutine[Any, Any, ResultT]]

    async def dispatch(self, event: EventT) -> ResultT:
        actions = list(self.planner(event))
        return await self.dispatch_actions(actions)

    def sync_hook(self) -> Callable[[EventT], None]:
        loop = asyncio.get_running_loop()

        async def dispatch_event(event: EventT) -> None:
            await self.dispatch(event)

        def hook(event: EventT) -> None:
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is loop:
                raise RuntimeError("Sync runtime event hook cannot run on its owner event loop thread")
            future = asyncio.run_coroutine_threadsafe(dispatch_event(event), loop)
            future.result()

        return hook
