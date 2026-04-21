import json
from pathlib import Path

from fastapi.testclient import TestClient

from eval.benchmarks.swe_verified.acceptance import evaluate_smoke_judge_payload, simulate_jsonrpc_request
from eval.benchmarks.swe_verified.acceptance import create_acceptance_app
from eval.harness.scenario import load_scenarios_from_dirs


def test_swe_verified_smoke_yaml_scenarios_load_with_benchmark_contracts():
    scenarios = load_scenarios_from_dirs([Path("eval/benchmarks")])
    scenario_ids = {scenario.id for scenario in scenarios}

    assert {"swe_verified_pytest_7521", "swe_verified_pytest_7571", "swe_verified_pytest_7490"} <= scenario_ids
    benchmark_scenarios = {scenario.id: scenario for scenario in scenarios if scenario.id.startswith("swe_verified_pytest_")}
    assert benchmark_scenarios["swe_verified_pytest_7521"].benchmark.family == "SWE-bench Verified"
    assert benchmark_scenarios["swe_verified_pytest_7521"].judge_config.type == "command"
    assert benchmark_scenarios["swe_verified_pytest_7521"].export.format == "predictions_json"


def test_swe_verified_acceptance_judge_fails_without_patch_marker():
    judged = evaluate_smoke_judge_payload(
        instance_id="pytest-dev__pytest-7571",
        payload={
            "result": {
                "final_response": "Unable to confirm the requested fix.",
                "artifacts": [
                    {"name": "final-response"},
                    {"name": "benchmark-instance"},
                    {"name": "workspace"},
                ],
            }
        },
    )

    assert judged["verdict"] == "failed"
    assert judged["scores"]["resolved"] == 0.0


def test_swe_verified_acceptance_jsonrpc_matches_fixtures():
    for request_name, response_name in (
        ("judge_request.json", "judge_response.json"),
        ("export_request.json", "export_response.json"),
    ):
        request_path = Path("eval/benchmarks/swe_verified/smoke/rpc") / request_name
        response_path = Path("eval/benchmarks/swe_verified/smoke/rpc") / response_name
        request = json.loads(request_path.read_text(encoding="utf-8"))
        expected = json.loads(response_path.read_text(encoding="utf-8"))

        assert simulate_jsonrpc_request(request) == expected


def test_swe_verified_acceptance_app_can_create_benchmark_batch():
    app = create_acceptance_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/monitor/evaluation/batches",
            headers={"Authorization": "Bearer token-1"},
            json={
                "agent_user_id": "agent-1",
                "scenario_ids": ["swe_verified_pytest_7521", "swe_verified_pytest_7571"],
                "sandbox": "local",
                "max_concurrent": 2,
            },
        )

    assert response.status_code == 200
    payload = response.json()["batch"]
    assert payload["kind"] == "benchmark_batch"
    assert payload["config_json"]["scenario_ids"] == ["swe_verified_pytest_7521", "swe_verified_pytest_7571"]
