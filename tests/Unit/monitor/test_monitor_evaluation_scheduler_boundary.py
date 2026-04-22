from backend.monitor.application.use_cases import evaluation as monitor_evaluation_service


class _FakeScheduler:
    def __init__(self):
        self.submitted = []

    def submit(self, spec):
        self.submitted.append(spec)


class _FakeBatchSvc:
    def get_batch_detail(self, _batch_id):
        return {
            "batch": {
                "batch_id": "batch-1",
                "agent_user_id": "agent-1",
                "config_json": {
                    "scenario_ids": ["scenario-1"],
                    "sandbox": "local",
                    "max_concurrent": 3,
                },
            },
            "runs": [],
        }

    def update_batch_status(self, batch_id, status):
        return {"batch_id": batch_id, "status": status}


def test_start_batch_submits_typed_spec_to_scheduler(monkeypatch):
    monkeypatch.setattr(monitor_evaluation_service.evaluation_read_service, "make_eval_batch_service", lambda: _FakeBatchSvc())
    monkeypatch.setattr(
        monitor_evaluation_service.evaluation_execution_service,
        "select_monitor_eval_scenarios",
        lambda scenario_ids, *, sandbox: [("scenario-stub", scenario_ids[0], sandbox)],
    )

    scheduler = _FakeScheduler()
    result = monitor_evaluation_service.start_monitor_evaluation_batch(
        "batch-1",
        execution_base_url="http://api/",
        token="tok",
        scheduler=scheduler,
    )

    assert result["accepted"] is True
    assert len(scheduler.submitted) == 1
    spec = scheduler.submitted[0]
    assert spec.batch_id == "batch-1"
    assert spec.execution_base_url == "http://api"
    assert spec.agent_user_id == "agent-1"
    assert spec.max_concurrent == 3
    assert spec.scenarios == [("scenario-stub", "scenario-1", "local")]
