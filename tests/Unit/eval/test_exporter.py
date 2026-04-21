from eval.exporter import build_batch_export


def test_build_batch_export_emits_predictions_bundle():
    payload = build_batch_export(
        batch={"batch_id": "batch-1", "config_json": {}, "kind": "benchmark_batch", "status": "completed"},
        aggregate={"pass_rate": 1.0},
        run_records=[
            {
                "run_id": "run-1",
                "scenario_id": "scenario-1",
                "run": {"run_id": "run-1", "final_response": "patch-body"},
                "benchmark": {"instance_id": "repo__1"},
                "judge_result": {"verdict": "passed"},
                "artifacts": [{"name": "final-response"}],
            }
        ],
        export_format="predictions_json",
    )

    assert payload["format"] == "predictions_json"
    assert payload["predictions"][0]["instance_id"] == "repo__1"
    assert payload["predictions"][0]["prediction"] == "patch-body"
