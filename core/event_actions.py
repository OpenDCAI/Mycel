from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


def plan_event_actions[EventT, ActionT](
    planners: Iterable[Callable[[EventT], Iterable[ActionT]]],
    event: EventT,
) -> list[ActionT]:
    current_planners = list(planners)
    if not current_planners:
        return []
    planned_actions: list[ActionT] = []
    for planner in current_planners:
        planned_actions.extend(planner(event))
    return planned_actions


def single_event_action_planner[EventT, ActionT](
    action: Callable[[EventT], ActionT],
) -> Callable[[EventT], list[ActionT]]:
    def plan(event: EventT) -> list[ActionT]:
        return [action(event)]

    return plan


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
