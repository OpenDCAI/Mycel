from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.web.core.dependencies import get_current_user_id
from backend.web.routers import monitor, resources
from backend.web.services import monitor_service, resource_service


def _stub_monitor_health(monkeypatch):
    payload = {
        "snapshot_at": "2026-04-07T00:00:00Z",
        "db": {
            "strategy": "supabase",
            "schema": "staging",
            "counts": {"chat_sessions": 0, "sandbox_leases": 0, "events": 0},
        },
        "sessions": {"total": 0, "providers": {}},
    }
    monkeypatch.setattr(monitor.monitor_service, "runtime_health_snapshot", lambda: payload)
    return payload


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
    payload = {
        "evaluations_running": 0,
        "latest_evaluation": {
            "status": "idle",
            "kind": "no_recorded_runs",
            "tone": "default",
            "headline": "No persisted evaluation runs are available yet.",
        },
    }
    monkeypatch.setattr(monitor.monitor_service, "get_monitor_evaluation_dashboard_summary", lambda: payload)
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

    monkeypatch.setattr(monitor, "get_monitor_resource_overview_snapshot", lambda: snapshot)
    monkeypatch.setattr(monitor, "refresh_monitor_resource_overview_sync", lambda: snapshot)
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
    monkeypatch.setattr(monitor, "refresh_monitor_resource_overview_sync", _refresh)

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


def test_monitor_health_route_smoke(monkeypatch):
    _stub_monitor_health(monkeypatch)

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/health")

    assert response.status_code == 200
    payload = response.json()
    assert "snapshot_at" in payload
    assert "db" in payload
    assert "sessions" in payload


def test_monitor_dashboard_route_smoke(monkeypatch):
    _stub_monitor_resource_snapshot(monkeypatch)
    _stub_monitor_health(monkeypatch)
    _stub_monitor_leases(monkeypatch)
    _stub_monitor_evaluation_summary(monkeypatch)

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert "snapshot_at" in payload
    assert "resources_summary" in payload
    assert "infra" in payload
    assert "workload" in payload
    assert "latest_evaluation" in payload


def test_monitor_leases_route_exposes_summary_and_groups(monkeypatch):
    _stub_monitor_leases(monkeypatch)
    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/leases")

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "groups" in payload
    assert "triage" in payload
    assert set(payload["summary"]).issuperset({"total", "healthy", "diverged", "orphan", "orphan_diverged"})
    assert isinstance(payload["groups"], list)
    assert set(payload["triage"]["summary"]).issuperset({"total", "active_drift", "detached_residue", "orphan_cleanup", "healthy_capacity"})
    assert isinstance(payload["triage"]["groups"], list)


def test_monitor_removed_forensic_routes_return_404():
    with TestClient(_build_monitor_test_app(), raise_server_exceptions=False) as client:
        thread_response = client.get("/api/monitor/thread/thread-404")
        threads_response = client.get("/api/monitor/threads")
        lease_response = client.get("/api/monitor/lease/lease-404")
        diverged_response = client.get("/api/monitor/diverged")
        events_response = client.get("/api/monitor/events", params={"limit": 25})
        event_response = client.get("/api/monitor/event/event-404")

    assert thread_response.status_code == 404
    assert threads_response.status_code == 404
    assert lease_response.status_code == 404
    assert diverged_response.status_code == 404
    assert events_response.status_code == 404
    assert event_response.status_code == 404


def test_monitor_evaluation_route_exposes_operator_truth(monkeypatch):
    monkeypatch.setattr(
        monitor_service,
        "get_monitor_evaluation_truth",
        lambda: {
            "status": "unavailable",
            "kind": "unavailable",
            "tone": "warning",
            "headline": "Evaluation operator truth is not wired in this runtime yet.",
            "summary": "Monitor can report that evaluation truth is unavailable without pretending nothing is happening.",
            "facts": [{"label": "Status", "value": "unavailable"}],
            "artifacts": [],
            "artifact_summary": {"present": 0, "missing": 0, "total": 0},
            "next_steps": ["Restore a truthful evaluation runtime source before reviving the monitor evaluation page."],
            "raw_notes": None,
        },
    )

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/evaluation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["kind"] == "unavailable"
    assert payload["headline"] == "Evaluation operator truth is not wired in this runtime yet."
    assert payload["artifact_summary"] == {"present": 0, "missing": 0, "total": 0}


def test_monitor_evaluation_route_exposes_latest_persisted_run(monkeypatch):
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
                }
            ]

        def get_metrics(self, run_id, tier=None):
            return [
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
            ]

    monkeypatch.setattr(monitor_service, "make_eval_store", lambda: FakeStore())
    _stub_monitor_resource_snapshot(monkeypatch)
    _stub_monitor_health(monkeypatch)
    _stub_monitor_leases(monkeypatch)

    with TestClient(_build_monitor_test_app()) as client:
        evaluation_response = client.get("/api/monitor/evaluation")
        dashboard_response = client.get("/api/monitor/dashboard")

    assert evaluation_response.status_code == 200
    evaluation_payload = evaluation_response.json()
    assert evaluation_payload["status"] == "completed"
    assert evaluation_payload["kind"] == "completed_recorded"
    assert evaluation_payload["headline"] == "Latest persisted evaluation run completed successfully."
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
    _stub_monitor_health(monkeypatch)
    _stub_monitor_leases(monkeypatch)
    monkeypatch.setattr(
        monitor_service,
        "get_monitor_evaluation_dashboard_summary",
        lambda: {
            "evaluations_running": 1,
            "latest_evaluation": {
                "status": "running",
                "kind": "running_active",
                "tone": "default",
                "headline": "Evaluation is actively running.",
            },
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


def test_monitor_resources_cleanup_route_forwards_structured_payload(monkeypatch):
    from backend.web.services import monitor_service

    monkeypatch.setattr(
        monitor_service,
        "cleanup_resource_leases",
        lambda *, action, lease_ids, expected_category: {
            "action": action,
            "expected_category": expected_category,
            "attempted": list(lease_ids),
            "cleaned": [{"lease_id": "lease-1", "category": expected_category}],
            "skipped": [],
            "errors": [],
            "refreshed_summary": {
                "total": 1,
                "active_drift": 0,
                "detached_residue": 0,
                "orphan_cleanup": 1,
                "healthy_capacity": 0,
            },
        },
    )

    with TestClient(_build_monitor_test_app()) as client:
        response = client.post(
            "/api/monitor/resources/cleanup",
            json={
                "action": "cleanup_residue",
                "lease_ids": ["lease-1"],
                "expected_category": "detached_residue",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "cleanup_residue"
    assert payload["attempted"] == ["lease-1"]
    assert payload["cleaned"] == [{"lease_id": "lease-1", "category": "detached_residue"}]
    assert payload["skipped"] == []
    assert payload["errors"] == []
    assert set(payload["refreshed_summary"]).issuperset({"total", "active_drift", "detached_residue", "orphan_cleanup", "healthy_capacity"})


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
