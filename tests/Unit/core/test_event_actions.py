from __future__ import annotations

import pytest

from core.event_actions import run_sync_actions


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
