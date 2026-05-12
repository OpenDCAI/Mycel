from __future__ import annotations

from collections.abc import Callable, Coroutine, Iterable
from typing import Any


async def run_planned_runtime_event[EventT, ActionT, ResultT](
    event: EventT,
    planner: Callable[[EventT], Iterable[ActionT]],
    dispatch_actions: Callable[[list[ActionT]], Coroutine[Any, Any, ResultT]],
) -> ResultT:
    actions = list(planner(event))
    return await dispatch_actions(actions)
