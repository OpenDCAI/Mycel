from __future__ import annotations

import pytest

from core.sync_callbacks import SyncActionRegistry


def test_sync_action_registry_runs_registered_actions_in_order() -> None:
    calls: list[tuple[str, str, int]] = []
    actions = SyncActionRegistry()

    def first(value: str, version: int) -> None:
        calls.append(("first", value, version))

    def second(value: str, version: int) -> None:
        calls.append(("second", value, version))

    actions.add(first)
    actions.add(second)
    actions.run("event-1", 3, on_error=lambda _exc: RuntimeError("wrapped"))

    assert calls == [
        ("first", "event-1", 3),
        ("second", "event-1", 3),
    ]


def test_sync_action_registry_wraps_first_action_failure() -> None:
    actions = SyncActionRegistry()

    def fail(_value: str) -> None:
        raise ValueError("runtime offline")

    actions.add(fail)
    with pytest.raises(RuntimeError) as exc_info:
        actions.run("event-1", on_error=lambda _exc: RuntimeError("callback failed"))

    assert str(exc_info.value) == "callback failed"
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_sync_action_registry_snapshots_actions_before_running() -> None:
    calls: list[str] = []
    actions = SyncActionRegistry()

    def first() -> None:
        calls.append("first")
        actions.add(second)

    def second() -> None:
        calls.append("second")

    actions.add(first)

    actions.run(on_error=lambda _exc: RuntimeError("wrapped"))

    assert calls == ["first"]
