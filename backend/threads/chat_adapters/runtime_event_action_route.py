from __future__ import annotations

from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeEventActionRoute[EventT, ActionT, ResultT]:
    planner: Callable[[EventT], Iterable[ActionT]]
    dispatch_actions: Callable[[Iterable[ActionT]], Coroutine[Any, Any, ResultT]]

    async def dispatch(self, event: EventT) -> ResultT:
        return await self.dispatch_actions(self.planner(event))
