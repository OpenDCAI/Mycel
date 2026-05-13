from __future__ import annotations

import pytest

from core.after_commit_actions import AfterCommitActions


class DomainActionError(RuntimeError):
    def __init__(self, row: dict[str, object]) -> None:
        super().__init__("domain action failed after commit")
        self.row = dict(row)


def test_after_commit_actions_run_registered_actions_in_order() -> None:
    calls: list[tuple[str, str, int]] = []
    actions = AfterCommitActions()

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


def test_after_commit_actions_wrap_first_action_failure() -> None:
    actions = AfterCommitActions()

    def fail(_value: str) -> None:
        raise ValueError("runtime offline")

    actions.add(fail)
    with pytest.raises(RuntimeError) as exc_info:
        actions.run("event-1", on_error=lambda _exc: RuntimeError("callback failed"))

    assert str(exc_info.value) == "callback failed"
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_after_commit_actions_snapshot_actions_before_running() -> None:
    calls: list[str] = []
    actions = AfterCommitActions()

    def first() -> None:
        calls.append("first")
        actions.add(second)

    def second() -> None:
        calls.append("second")

    actions.add(first)

    actions.run(on_error=lambda _exc: RuntimeError("wrapped"))

    assert calls == ["first"]


def test_after_commit_action_failure_does_not_roll_back_prior_commit() -> None:
    rows: dict[str, dict[str, object]] = {}
    actions = AfterCommitActions()

    def create_row(value: str) -> dict[str, object]:
        row: dict[str, object] = {"id": "row-1", "value": value}
        rows[str(row["id"])] = dict(row)
        actions.run(row, on_error=lambda _exc: DomainActionError(row))
        return row

    def fail_after_commit(_row: dict[str, object]) -> None:
        raise RuntimeError("runtime offline")

    actions.add(fail_after_commit)

    with pytest.raises(DomainActionError) as exc_info:
        create_row("persisted")

    assert exc_info.value.row == {"id": "row-1", "value": "persisted"}
    assert str(exc_info.value.__cause__) == "runtime offline"
    assert rows["row-1"] == {"id": "row-1", "value": "persisted"}
