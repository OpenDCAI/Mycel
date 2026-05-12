from __future__ import annotations

import pytest

from core.event_actions import plan_event_actions, run_sync_actions


def test_plan_event_actions_flattens_planners_in_order() -> None:
    def first(value: str) -> list[str]:
        return [f"first:{value}", f"first-again:{value}"]

    def second(value: str) -> list[str]:
        return [f"second:{value}"]

    actions = plan_event_actions([first, second], "event-1")

    assert actions == ["first:event-1", "first-again:event-1", "second:event-1"]


def test_plan_event_actions_snapshots_planners_before_running() -> None:
    planners = []

    def first(value: str) -> list[str]:
        planners.append(second)
        return [f"first:{value}"]

    def second(value: str) -> list[str]:
        return [f"second:{value}"]

    planners.append(first)

    actions = plan_event_actions(planners, "event-1")

    assert actions == ["first:event-1"]


def test_run_sync_actions_runs_registered_actions_in_order() -> None:
    calls: list[tuple[str, str, int]] = []

    def first(value: str, version: int) -> None:
        calls.append(("first", value, version))

    def second(value: str, version: int) -> None:
        calls.append(("second", value, version))

    run_sync_actions([first, second], "event-1", 3, on_error=lambda _exc: RuntimeError("wrapped"))

    assert calls == [
        ("first", "event-1", 3),
        ("second", "event-1", 3),
    ]


def test_run_sync_actions_wraps_first_action_failure() -> None:
    def fail(_value: str) -> None:
        raise ValueError("runtime offline")

    with pytest.raises(RuntimeError) as exc_info:
        run_sync_actions([fail], "event-1", on_error=lambda _exc: RuntimeError("action failed"))

    assert str(exc_info.value) == "action failed"
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_run_sync_actions_snapshots_actions_before_running() -> None:
    calls: list[str] = []
    actions = []

    def first() -> None:
        calls.append("first")
        actions.append(second)

    def second() -> None:
        calls.append("second")

    actions.append(first)

    run_sync_actions(actions, on_error=lambda _exc: RuntimeError("wrapped"))

    assert calls == ["first"]
