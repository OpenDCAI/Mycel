from __future__ import annotations

import pytest

from core.sync_callbacks import run_sync_callbacks


def test_run_sync_callbacks_runs_registered_callbacks_in_order() -> None:
    calls: list[tuple[str, str, int]] = []

    def first(value: str, version: int) -> None:
        calls.append(("first", value, version))

    def second(value: str, version: int) -> None:
        calls.append(("second", value, version))

    run_sync_callbacks([first, second], "event-1", 3, on_error=lambda _exc: RuntimeError("wrapped"))

    assert calls == [
        ("first", "event-1", 3),
        ("second", "event-1", 3),
    ]


def test_run_sync_callbacks_wraps_first_callback_failure() -> None:
    def fail(_value: str) -> None:
        raise ValueError("runtime offline")

    with pytest.raises(RuntimeError) as exc_info:
        run_sync_callbacks([fail], "event-1", on_error=lambda _exc: RuntimeError("callback failed"))

    assert str(exc_info.value) == "callback failed"
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_run_sync_callbacks_snapshots_callbacks_before_running() -> None:
    calls: list[str] = []
    callbacks = []

    def first() -> None:
        calls.append("first")
        callbacks.append(second)

    def second() -> None:
        calls.append("second")

    callbacks.append(first)

    run_sync_callbacks(callbacks, on_error=lambda _exc: RuntimeError("wrapped"))

    assert calls == ["first"]
