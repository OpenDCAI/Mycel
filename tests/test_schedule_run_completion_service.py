from __future__ import annotations

import pytest

from backend.web.services import schedule_run_completion_service


class FakeScheduleService:
    def __init__(self) -> None:
        self.runs = {
            "schedule_run_1": {
                "id": "schedule_run_1",
                "status": "running",
                "output_json": {"routing": {"run_id": "runtime_run_1"}},
            }
        }
        self.updates: list[tuple[str, dict]] = []

    def get_schedule_run(self, run_id: str) -> dict | None:
        return self.runs.get(run_id)

    def update_schedule_run(self, run_id: str, **fields) -> dict | None:
        self.updates.append((run_id, fields))
        self.runs[run_id].update(fields)
        return self.runs[run_id]


def test_complete_schedule_run_marks_success_and_preserves_routing_output(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeScheduleService()
    monkeypatch.setattr(schedule_run_completion_service, "schedule_service", service)

    schedule_run_completion_service.complete_schedule_run_from_runtime(
        "schedule_run_1",
        source="schedule",
        status="succeeded",
        runtime_run_id="runtime_run_1",
        thread_id="thread_1",
    )

    assert service.updates[0][0] == "schedule_run_1"
    fields = service.updates[0][1]
    assert fields["status"] == "succeeded"
    assert "completed_at" in fields
    assert fields["error"] is None
    assert fields["output_json"] == {
        "routing": {"run_id": "runtime_run_1"},
        "runtime": {"run_id": "runtime_run_1", "thread_id": "thread_1", "status": "succeeded"},
    }


def test_schedule_source_without_schedule_run_id_fails_loudly() -> None:
    with pytest.raises(RuntimeError, match="schedule_run_id"):
        schedule_run_completion_service.complete_schedule_run_from_runtime(
            None,
            source="schedule",
            status="succeeded",
            runtime_run_id="runtime_run_1",
            thread_id="thread_1",
        )


def test_non_schedule_run_without_schedule_run_id_noops(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeScheduleService()
    monkeypatch.setattr(schedule_run_completion_service, "schedule_service", service)

    schedule_run_completion_service.complete_schedule_run_from_runtime(
        None,
        source="owner",
        status="succeeded",
        runtime_run_id="runtime_run_1",
        thread_id="thread_1",
    )

    assert service.updates == []
