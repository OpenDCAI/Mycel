from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.web.core.dependencies import get_current_user_id
from backend.web.routers import monitor, resources
from backend.web.services import monitor_service, resource_service


def _stub_monitor_leases(monkeypatch):
    payload = {
        "summary": {
            "total": 0,
            "healthy": 0,
            "diverged": 0,
            "orphan": 0,
            "orphan_diverged": 0,
        },
        "groups": [],
        "triage": {
            "summary": {
                "total": 0,
                "active_drift": 0,
                "detached_residue": 0,
                "orphan_cleanup": 0,
                "healthy_capacity": 0,
            },
            "groups": [],
        },
    }
    monkeypatch.setattr(monitor.monitor_service, "list_leases", lambda: payload)
    return payload


def _stub_monitor_evaluation_summary(monkeypatch):
    evaluation_truth = {
        "status": "idle",
        "kind": "no_recorded_runs",
        "tone": "default",
        "headline": "No persisted evaluation runs are available yet.",
        "summary": "Evaluation storage is wired, but there are no recorded runs to report yet.",
        "facts": [{"label": "Status", "value": "idle"}],
        "artifacts": [],
        "artifact_summary": {"present": 0, "missing": 0, "total": 0},
        "next_steps": ["Run an evaluation to populate the operator surface with persisted runtime truth."],
        "raw_notes": None,
    }
    payload = {
        "evaluations_running": 0,
        "latest_evaluation": {
            "status": evaluation_truth["status"],
            "kind": evaluation_truth["kind"],
            "tone": evaluation_truth["tone"],
            "headline": evaluation_truth["headline"],
        },
    }
    monkeypatch.setattr(monitor.monitor_service, "get_monitor_evaluation_truth", lambda: evaluation_truth)
    return payload


def _build_monitor_test_app(*, include_product_resources: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(monitor.router)
    if include_product_resources:
        app.include_router(resources.router)
        app.dependency_overrides[get_current_user_id] = lambda: "user-test"
    return app


def _stub_monitor_resource_snapshot(monkeypatch):
    snapshot = {
        "summary": {
            "snapshot_at": "2026-04-07T00:00:00Z",
            "last_refreshed_at": "2026-04-07T00:00:00Z",
            "refresh_status": "fresh",
            "running_sessions": 0,
            "active_providers": 0,
            "unavailable_providers": 0,
        },
        "providers": [],
        "triage": {
            "summary": {
                "total": 0,
                "active_drift": 0,
                "detached_residue": 0,
                "orphan_cleanup": 0,
                "healthy_capacity": 0,
            },
            "groups": [],
        },
    }

    monkeypatch.setattr(monitor, "get_resource_overview_snapshot", lambda: snapshot)
    monkeypatch.setattr(monitor, "refresh_resource_overview_sync", lambda: snapshot)
    monkeypatch.setattr(resource_service, "refresh_resource_snapshots", lambda: {"probed": 0, "errors": 0})
    return snapshot


def test_monitor_resources_route_smoke(monkeypatch):
    _stub_monitor_resource_snapshot(monkeypatch)

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/resources")

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "providers" in payload
    assert "triage" in payload
    assert "snapshot_at" in payload["summary"]
    assert "running_sessions" in payload["summary"]
    assert isinstance(payload["providers"], list)
    assert set(payload["triage"]["summary"]).issuperset({"total", "active_drift", "detached_residue", "orphan_cleanup", "healthy_capacity"})
    assert isinstance(payload["triage"]["groups"], list)


def test_monitor_resources_refresh_route_smoke(monkeypatch):
    _stub_monitor_resource_snapshot(monkeypatch)

    with TestClient(_build_monitor_test_app()) as client:
        response = client.post("/api/monitor/resources/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "providers" in payload
    assert "triage" in payload
    assert "last_refreshed_at" in payload["summary"]
    assert "refresh_status" in payload["summary"]
    assert set(payload["triage"]["summary"]).issuperset({"total", "active_drift", "detached_residue", "orphan_cleanup", "healthy_capacity"})


def test_monitor_resources_cleanup_route_is_not_part_of_active_surface(monkeypatch):
    _stub_monitor_resource_snapshot(monkeypatch)

    with TestClient(_build_monitor_test_app(), raise_server_exceptions=False) as client:
        response = client.post(
            "/api/monitor/resources/cleanup",
            json={
                "action": "cleanup_residue",
                "lease_ids": ["lease-1"],
                "expected_category": "detached_residue",
            },
        )

    assert response.status_code == 404


def test_monitor_resources_refresh_route_probes_before_refresh(monkeypatch):
    calls: list[str] = []
    snapshot = {
        "summary": {
            "snapshot_at": "2026-04-07T00:00:00Z",
            "last_refreshed_at": "2026-04-07T00:00:00Z",
            "refresh_status": "fresh",
            "running_sessions": 0,
            "active_providers": 0,
            "unavailable_providers": 0,
        },
        "providers": [],
        "triage": {
            "summary": {
                "total": 0,
                "active_drift": 0,
                "detached_residue": 0,
                "orphan_cleanup": 0,
                "healthy_capacity": 0,
            },
            "groups": [],
        },
    }

    def _probe():
        calls.append("probe")
        return {"probed": 1, "errors": 0}

    def _refresh():
        calls.append("refresh")
        return snapshot

    monkeypatch.setattr(resource_service, "refresh_resource_snapshots", _probe)
    monkeypatch.setattr(monitor, "refresh_resource_overview_sync", _refresh)

    with TestClient(_build_monitor_test_app()) as client:
        response = client.post("/api/monitor/resources/refresh")

    assert response.status_code == 200
    assert response.json() == snapshot
    assert calls == ["probe", "refresh"]


def test_monitor_and_product_resource_routes_coexist_intentionally(monkeypatch):
    from backend.web.services import resource_projection_service

    _stub_monitor_resource_snapshot(monkeypatch)
    monkeypatch.setattr(
        resource_projection_service,
        "list_user_resource_providers",
        lambda *_args, **_kwargs: {"summary": {"snapshot_at": "now"}, "providers": []},
    )

    with TestClient(_build_monitor_test_app(include_product_resources=True)) as client:
        monitor_response = client.get("/api/monitor/resources")
        product_response = client.get("/api/resources/overview")

    assert monitor_response.status_code == 200
    assert product_response.status_code == 200


def test_monitor_dashboard_route_smoke(monkeypatch):
    resources = _stub_monitor_resource_snapshot(monkeypatch)
    _stub_monitor_leases(monkeypatch)
    _stub_monitor_evaluation_summary(monkeypatch)
    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot_at"] == resources["summary"]["snapshot_at"]
    assert "infra" in payload
    assert "workload" in payload
    assert "latest_evaluation" in payload
    assert "resources_summary" not in payload
    assert "leases_healthy" not in payload["infra"]
    assert "db_sessions_total" not in payload["workload"]
    assert "provider_sessions_total" not in payload["workload"]


def test_monitor_leases_route_exposes_summary_and_groups(monkeypatch):
    _stub_monitor_leases(monkeypatch)
    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/leases")

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "groups" in payload


def test_monitor_lease_detail_route_exposes_structured_operator_truth(monkeypatch):
    monkeypatch.setattr(
        monitor_service,
        "get_monitor_lease_detail",
        lambda lease_id: {
            "lease": {"lease_id": lease_id, "provider_name": "daytona", "desired_state": "running", "observed_state": "running"},
            "triage": {"category": "healthy_capacity", "title": "Healthy Capacity"},
            "provider": {"id": "daytona", "name": "daytona"},
            "runtime": {"runtime_session_id": "rt-1"},
            "threads": [{"thread_id": "thread-1"}],
            "sessions": [{"chat_session_id": "cs-1", "thread_id": "thread-1", "status": "active"}],
        },
    )

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/leases/lease-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["lease"]["lease_id"] == "lease-1"
    assert payload["provider"] == {"id": "daytona", "name": "daytona"}
    assert payload["runtime"] == {"runtime_session_id": "rt-1"}
    assert payload["threads"] == [{"thread_id": "thread-1"}]
    assert payload["sessions"] == [{"chat_session_id": "cs-1", "thread_id": "thread-1", "status": "active"}]
    assert payload["triage"] == {"category": "healthy_capacity", "title": "Healthy Capacity"}


def test_monitor_lease_cleanup_route_returns_operation_truth(monkeypatch):
    monkeypatch.setattr(
        monitor_service,
        "request_monitor_lease_cleanup",
        lambda lease_id: {
            "accepted": True,
            "message": "Lease cleanup completed.",
            "operation": {
                "operation_id": "op-1",
                "kind": "lease_cleanup",
                "target_type": "lease",
                "target_id": lease_id,
                "status": "succeeded",
            },
            "current_truth": {"lease_id": lease_id, "triage_category": "orphan_cleanup"},
        },
    )

    with TestClient(_build_monitor_test_app()) as client:
        response = client.post("/api/monitor/leases/lease-1/cleanup")

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["operation"]["kind"] == "lease_cleanup"
    assert payload["operation"]["target_type"] == "lease"
    assert payload["operation"]["target_id"] == "lease-1"


def test_monitor_operation_detail_route_reads_operation_truth(monkeypatch):
    monkeypatch.setattr(
        monitor_service,
        "get_monitor_operation_detail",
        lambda operation_id: {
            "operation": {
                "operation_id": operation_id,
                "kind": "lease_cleanup",
                "status": "succeeded",
                "summary": "Lease cleanup completed",
            },
            "target": {"target_type": "lease", "target_id": "lease-1"},
            "result_truth": {"runtime_state_after": None},
            "events": [{"status": "succeeded", "message": "Lease cleanup completed"}],
        },
    )

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/operations/op-1")

    assert response.status_code == 200
    assert response.json()["operation"]["operation_id"] == "op-1"

def test_monitor_lease_detail_route_maps_missing_lease_to_404(monkeypatch):
    monkeypatch.setattr(
        monitor_service,
        "get_monitor_lease_detail",
        lambda lease_id: (_ for _ in ()).throw(KeyError(f"Lease not found: {lease_id}")),
    )

    with TestClient(_build_monitor_test_app(), raise_server_exceptions=False) as client:
        response = client.get("/api/monitor/leases/lease-404")

    assert response.status_code == 404
    assert "Lease not found: lease-404" in response.text


def test_monitor_provider_detail_route_exposes_structured_operator_truth(monkeypatch):
    monkeypatch.setattr(
        monitor_service,
        "get_monitor_provider_detail",
        lambda provider_id: {
            "provider": {"id": provider_id, "name": "daytona"},
            "lease_ids": ["lease-1"],
            "thread_ids": ["thread-1"],
            "runtime_session_ids": ["runtime-1"],
        },
    )

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/providers/daytona")

    assert response.status_code == 200
    assert response.json() == {
        "provider": {"id": "daytona", "name": "daytona"},
        "lease_ids": ["lease-1"],
        "thread_ids": ["thread-1"],
        "runtime_session_ids": ["runtime-1"],
    }


def test_monitor_runtime_detail_route_exposes_structured_operator_truth(monkeypatch):
    monkeypatch.setattr(
        monitor_service,
        "get_monitor_runtime_detail",
        lambda runtime_session_id: {
            "provider": {"id": "daytona"},
            "runtime": {"runtimeSessionId": runtime_session_id, "status": "running"},
            "lease_id": "lease-1",
            "thread_id": "thread-1",
        },
    )

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/runtimes/runtime-1")

    assert response.status_code == 200
    assert response.json() == {
        "provider": {"id": "daytona"},
        "runtime": {"runtimeSessionId": "runtime-1", "status": "running"},
        "lease_id": "lease-1",
        "thread_id": "thread-1",
    }


def test_monitor_thread_detail_route_exposes_structured_operator_truth(monkeypatch):
    async def _thread_detail(_app, thread_id):
        return {
            "thread": {"id": thread_id, "agent_user_id": "agent-1"},
            "owner": {"agent_user_id": "agent-1", "agent_name": "Toad"},
            "summary": {"thread_id": thread_id, "lease_id": "lease-1"},
            "sessions": [{"chat_session_id": "cs-1", "lease_id": "lease-1"}],
            "trajectory": {
                "run_id": "run-1",
                "conversation": [{"role": "human", "text": "hello"}],
                "events": [{"seq": 1, "event_type": "tool_call", "actor": "tool", "summary": "terminal"}],
            },
        }

    monkeypatch.setattr(
        monitor_service,
        "get_monitor_thread_detail",
        _thread_detail,
    )

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/threads/thread-1")

    assert response.status_code == 200
    assert response.json() == {
        "thread": {"id": "thread-1", "agent_user_id": "agent-1"},
        "owner": {"agent_user_id": "agent-1", "agent_name": "Toad"},
        "summary": {"thread_id": "thread-1", "lease_id": "lease-1"},
        "sessions": [{"chat_session_id": "cs-1", "lease_id": "lease-1"}],
        "trajectory": {
            "run_id": "run-1",
            "conversation": [{"role": "human", "text": "hello"}],
            "events": [{"seq": 1, "event_type": "tool_call", "actor": "tool", "summary": "terminal"}],
        },
    }


def test_monitor_threads_route_exposes_thread_workbench(monkeypatch):
    expected = {
        "threads": [
            {
                "thread_id": "thread-1",
                "sandbox": "daytona",
                "agent_name": "Planner",
                "agent_user_id": "member-1",
                "branch_index": 0,
                "sidebar_label": "Main",
                "avatar_url": "/api/entities/member-1/avatar",
                "is_main": True,
                "running": True,
                "updated_at": "2026-04-10T12:00:00Z",
            }
        ]
    }
    monkeypatch.setattr(monitor_service, "list_monitor_threads", lambda _app, _user_id: expected)

    app = _build_monitor_test_app()
    app.dependency_overrides[monitor.get_current_user_id] = lambda: "owner-1"

    try:
        with TestClient(app) as client:
            response = client.get("/api/monitor/threads")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == expected


def test_monitor_provider_runtime_and_thread_detail_routes_map_missing_rows_to_404(monkeypatch):
    monkeypatch.setattr(
        monitor_service,
        "get_monitor_provider_detail",
        lambda provider_id: (_ for _ in ()).throw(KeyError(f"Provider not found: {provider_id}")),
    )
    monkeypatch.setattr(
        monitor_service,
        "get_monitor_runtime_detail",
        lambda runtime_session_id: (_ for _ in ()).throw(KeyError(f"Runtime not found: {runtime_session_id}")),
    )
    async def _missing_thread(_app, thread_id):
        raise KeyError(f"Thread not found: {thread_id}")

    monkeypatch.setattr(
        monitor_service,
        "get_monitor_thread_detail",
        _missing_thread,
    )

    with TestClient(_build_monitor_test_app(), raise_server_exceptions=False) as client:
        provider_response = client.get("/api/monitor/providers/ghost")
        runtime_response = client.get("/api/monitor/runtimes/runtime-404")
        thread_response = client.get("/api/monitor/threads/thread-404")

    assert provider_response.status_code == 404
    assert "Provider not found: ghost" in provider_response.text
    assert runtime_response.status_code == 404
    assert "Runtime not found: runtime-404" in runtime_response.text
    assert thread_response.status_code == 404
    assert "Thread not found: thread-404" in thread_response.text

def test_monitor_removed_forensic_routes_return_404():
    with TestClient(_build_monitor_test_app(), raise_server_exceptions=False) as client:
        health_response = client.get("/api/monitor/health")
        thread_response = client.get("/api/monitor/thread/thread-404")
        lease_response = client.get("/api/monitor/lease/lease-404")
        diverged_response = client.get("/api/monitor/diverged")
        events_response = client.get("/api/monitor/events", params={"limit": 25})
        event_response = client.get("/api/monitor/event/event-404")

    assert health_response.status_code == 404
    assert thread_response.status_code == 404
    assert lease_response.status_code == 404
    assert diverged_response.status_code == 404
    assert events_response.status_code == 404
    assert event_response.status_code == 404


def test_monitor_evaluation_route_exposes_operator_truth(monkeypatch):
    monkeypatch.setattr(
        monitor_service,
        "get_monitor_evaluation_workbench",
        lambda: {
            "headline": "Evaluation Workbench",
            "summary": "No persisted evaluation runs are available yet.",
            "overview": {
                "total_runs": 0,
                "running_runs": 0,
                "completed_runs": 0,
                "failed_runs": 0,
            },
            "runs": [],
            "selected_run": None,
            "limitations": ["Run an evaluation to populate the workbench with persisted runtime truth."],
        },
    )

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/evaluation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["headline"] == "Evaluation Workbench"
    assert payload["summary"] == "No persisted evaluation runs are available yet."
    assert payload["overview"] == {
        "total_runs": 0,
        "running_runs": 0,
        "completed_runs": 0,
        "failed_runs": 0,
    }
    assert payload["runs"] == []
    assert payload["selected_run"] is None


def test_monitor_evaluation_route_exposes_recent_persisted_runs(monkeypatch):
    class FakeStore:
        def list_runs(self, thread_id=None, limit=50):
            return [
                {
                    "id": "run-1",
                    "thread_id": "thread-eval",
                    "started_at": "2026-04-08T00:00:00Z",
                    "finished_at": "2026-04-08T00:03:00Z",
                    "status": "completed",
                    "user_message": "solve the eval task",
                },
                {
                    "id": "run-2",
                    "thread_id": "thread-eval-2",
                    "started_at": "2026-04-09T00:00:00Z",
                    "finished_at": None,
                    "status": "running",
                    "user_message": "keep the benchmark running",
                }
            ]

        def get_metrics(self, run_id, tier=None):
            metrics = {
                "run-1": [
                    {
                        "id": "metric-1",
                        "tier": "system",
                        "timestamp": "2026-04-08T00:03:01Z",
                        "metrics": {
                            "total_tokens": 123,
                            "llm_call_count": 3,
                            "tool_call_count": 2,
                        },
                    }
                ],
                "run-2": [
                    {
                        "id": "metric-2",
                        "tier": "system",
                        "timestamp": "2026-04-09T00:03:01Z",
                        "metrics": {
                            "total_tokens": 456,
                            "llm_call_count": 5,
                            "tool_call_count": 4,
                        },
                    }
                ],
            }
            return metrics[run_id]

    monkeypatch.setattr(monitor_service, "make_eval_store", lambda: FakeStore())
    _stub_monitor_resource_snapshot(monkeypatch)
    _stub_monitor_leases(monkeypatch)

    with TestClient(_build_monitor_test_app()) as client:
        evaluation_response = client.get("/api/monitor/evaluation")
        dashboard_response = client.get("/api/monitor/dashboard")

    assert evaluation_response.status_code == 200
    evaluation_payload = evaluation_response.json()
    assert evaluation_payload["headline"] == "Evaluation Workbench"
    assert evaluation_payload["overview"] == {
        "total_runs": 2,
        "running_runs": 1,
        "completed_runs": 1,
        "failed_runs": 0,
    }
    assert [run["run_id"] for run in evaluation_payload["runs"]] == ["run-1", "run-2"]
    assert evaluation_payload["selected_run"] == {
        "run_id": "run-1",
        "thread_id": "thread-eval",
        "status": "completed",
        "started_at": "2026-04-08T00:00:00Z",
        "finished_at": "2026-04-08T00:03:00Z",
        "user_message": "solve the eval task",
        "facts": [
            {"label": "Metric Tiers", "value": "1"},
            {"label": "Total tokens", "value": "123"},
            {"label": "LLM calls", "value": "3"},
            {"label": "Tool calls", "value": "2"},
        ],
    }
    assert dashboard_response.status_code == 200
    dashboard_payload = dashboard_response.json()
    assert dashboard_payload["workload"]["evaluations_running"] == 0
    assert dashboard_payload["latest_evaluation"] == {
        "status": "completed",
        "kind": "completed_recorded",
        "tone": "success",
        "headline": "Latest persisted evaluation run completed successfully.",
    }


def test_monitor_dashboard_route_derives_evaluation_summary_from_service(monkeypatch):
    _stub_monitor_resource_snapshot(monkeypatch)
    _stub_monitor_leases(monkeypatch)
    monkeypatch.setattr(
        monitor_service,
        "get_monitor_evaluation_truth",
        lambda: {
            "status": "running",
            "kind": "running_active",
            "tone": "default",
            "headline": "Evaluation is actively running.",
        },
    )

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workload"]["evaluations_running"] == 1
    assert payload["latest_evaluation"] == {
        "status": "running",
        "kind": "running_active",
        "tone": "default",
        "headline": "Evaluation is actively running.",
    }

def test_monitor_sandbox_browse_route_maps_missing_lease_to_404(monkeypatch):
    def _raise(_lease_id, _path):
        raise KeyError("Lease not found: lease-404")

    monkeypatch.setattr(resource_service, "sandbox_browse", _raise)

    with TestClient(_build_monitor_test_app(), raise_server_exceptions=False) as client:
        response = client.get("/api/monitor/sandbox/lease-404/browse", params={"path": "/"})

    assert response.status_code == 404
    assert "Lease not found: lease-404" in response.text


def test_monitor_sandbox_browse_route_maps_runtime_failures_to_503(monkeypatch):
    def _raise(_lease_id, _path):
        raise RuntimeError("Could not initialize provider: daytona_selfhost")

    monkeypatch.setattr(resource_service, "sandbox_browse", _raise)

    with TestClient(_build_monitor_test_app(), raise_server_exceptions=False) as client:
        response = client.get("/api/monitor/sandbox/lease-1/browse", params={"path": "/"})

    assert response.status_code == 503
    assert "Could not initialize provider: daytona_selfhost" in response.text


def test_monitor_sandbox_read_route_maps_missing_lease_to_404(monkeypatch):
    def _raise(_lease_id, _path):
        raise KeyError("Lease not found: lease-404")

    monkeypatch.setattr(resource_service, "sandbox_read", _raise)

    with TestClient(_build_monitor_test_app(), raise_server_exceptions=False) as client:
        response = client.get("/api/monitor/sandbox/lease-404/read", params={"path": "/README.md"})

    assert response.status_code == 404
    assert "Lease not found: lease-404" in response.text


def test_monitor_sandbox_read_route_maps_runtime_failures_to_503(monkeypatch):
    def _raise(_lease_id, _path):
        raise RuntimeError("No active instance for this lease — sandbox may be destroyed or paused")

    monkeypatch.setattr(resource_service, "sandbox_read", _raise)

    with TestClient(_build_monitor_test_app(), raise_server_exceptions=False) as client:
        response = client.get("/api/monitor/sandbox/lease-1/read", params={"path": "/README.md"})

    assert response.status_code == 503
    assert "No active instance for this lease" in response.text
