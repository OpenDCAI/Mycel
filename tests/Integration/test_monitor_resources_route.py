import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.web.core.dependencies import get_current_user_id
from backend.web.routers import monitor, resources
from backend.web.services import monitor_service, resource_service


def _app(*, include_product_resources: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(monitor.router)
    if include_product_resources:
        app.include_router(resources.router)
        app.dependency_overrides[get_current_user_id] = lambda: "owner-1"
    return app


def _request(method: str, path: str, *, app: FastAPI | None = None, raise_server_exceptions: bool = True, **kwargs):
    with TestClient(app or _app(), raise_server_exceptions=raise_server_exceptions) as client:
        return getattr(client, method)(path, **kwargs)


def _resource_snapshot() -> dict:
    return {
        "summary": {
            "snapshot_at": "2026-04-07T00:00:00Z",
            "last_refreshed_at": "2026-04-07T00:00:00Z",
            "refresh_status": "fresh",
            "running_sessions": 1,
            "active_providers": 1,
            "unavailable_providers": 0,
        },
        "providers": [{"id": "local", "sessions": []}],
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


def _stub_dashboard_dependencies(monkeypatch):
    monkeypatch.setattr(monitor, "get_resource_overview_snapshot", _resource_snapshot)
    monkeypatch.setattr(
        monitor.monitor_service,
        "list_monitor_sandboxes",
        lambda: {
            "summary": {"total": 2, "diverged": 1, "orphan": 0, "orphan_diverged": 0},
            "groups": [],
            "triage": {"summary": {}, "groups": []},
        },
    )
    monkeypatch.setattr(
        monitor.monitor_service,
        "get_monitor_evaluation_workbench",
        lambda: {
            "summary": "Recent persisted evaluation runs and their runtime state.",
            "overview": {"running_runs": 1},
            "selected_run": {"run_id": "run-1", "status": "running"},
        },
    )


def test_monitor_resources_refresh_probes_before_rebuilding_snapshot(monkeypatch):
    calls: list[str] = []

    def _probe():
        calls.append("probe")
        return {"probed": 1, "errors": 0}

    def _refresh():
        calls.append("refresh")
        return _resource_snapshot()

    monkeypatch.setattr(resource_service, "refresh_resource_snapshots", _probe)
    monkeypatch.setattr(monitor, "refresh_resource_overview_sync", _refresh)

    response = _request("post", "/api/monitor/resources/refresh")

    assert response.status_code == 200
    assert response.json()["summary"]["refresh_status"] == "fresh"
    assert calls == ["probe", "refresh"]


def test_monitor_and_product_resource_routes_coexist(monkeypatch):
    from backend.web.services import resource_projection_service

    monkeypatch.setattr(monitor, "get_resource_overview_snapshot", _resource_snapshot)
    monkeypatch.setattr(
        resource_projection_service,
        "list_user_resource_providers",
        lambda *_args, **_kwargs: {"summary": {"snapshot_at": "now"}, "providers": []},
    )

    with TestClient(_app(include_product_resources=True)) as client:
        monitor_response = client.get("/api/monitor/resources")
        product_response = client.get("/api/resources/overview")

    assert monitor_response.status_code == 200
    assert product_response.status_code == 200


def test_monitor_dashboard_uses_service_summaries(monkeypatch):
    _stub_dashboard_dependencies(monkeypatch)
    monkeypatch.setattr(
        monitor.monitor_service,
        "list_leases",
        lambda: (_ for _ in ()).throw(AssertionError("dashboard should not use legacy lease shell")),
    )

    response = _request("get", "/api/monitor/dashboard")

    assert response.status_code == 200
    assert response.json() == {
        "snapshot_at": "2026-04-07T00:00:00Z",
        "infra": {
            "providers_active": 1,
            "providers_unavailable": 0,
            "sandboxes_total": 2,
            "sandboxes_diverged": 1,
            "sandboxes_orphan": 0,
        },
        "workload": {"running_sessions": 1, "evaluations_running": 1},
        "latest_evaluation": {
            "run_id": "run-1",
            "status": "running",
            "headline": "Recent persisted evaluation runs and their runtime state.",
        },
    }


@pytest.mark.parametrize(
    ("method", "path", "service_name", "payload"),
    [
        ("get", "/api/monitor/leases", "list_leases", {"summary": {}, "groups": []}),
        ("get", "/api/monitor/sandboxes", "list_monitor_sandboxes", {"summary": {}, "groups": [], "items": []}),
        ("get", "/api/monitor/provider-sessions", "list_monitor_provider_sessions", {"sessions": [], "count": 0}),
        ("get", "/api/monitor/providers/daytona", "get_monitor_provider_detail", {"provider": {"id": "daytona"}}),
        ("get", "/api/monitor/leases/lease-1", "get_monitor_lease_detail", {"lease": {"lease_id": "lease-1"}}),
        ("get", "/api/monitor/sandboxes/sandbox-1", "get_monitor_sandbox_detail", {"sandbox": {"sandbox_id": "sandbox-1"}}),
        ("post", "/api/monitor/sandboxes/sandbox-1/cleanup", "request_monitor_sandbox_cleanup", {"accepted": True}),
        (
            "post",
            "/api/monitor/provider-sessions/daytona_selfhost/session-1/cleanup",
            "request_monitor_provider_session_cleanup",
            {"accepted": True},
        ),
        ("get", "/api/monitor/operations/op-1", "get_monitor_operation_detail", {"operation": {"operation_id": "op-1"}}),
        ("get", "/api/monitor/runtimes/runtime-1", "get_monitor_runtime_detail", {"runtime": {"runtimeSessionId": "runtime-1"}}),
        ("get", "/api/monitor/sandbox-configs", "get_monitor_sandbox_configs", {"providers": [], "count": 0}),
        ("get", "/api/monitor/evaluation", "get_monitor_evaluation_workbench", {"headline": "Evaluation Workbench"}),
        ("get", "/api/monitor/evaluation/batches", "get_monitor_evaluation_batches", {"items": [], "count": 0}),
        ("get", "/api/monitor/evaluation/scenarios", "get_monitor_evaluation_scenarios", {"items": [], "count": 0}),
        ("get", "/api/monitor/evaluation/batches/batch-1", "get_monitor_evaluation_batch_detail", {"batch": {"batch_id": "batch-1"}}),
        ("get", "/api/monitor/evaluation/runs/run-1", "get_monitor_evaluation_run_detail", {"run": {"run_id": "run-1"}}),
    ],
)
def test_monitor_routes_delegate_to_service(monkeypatch, method, path, service_name, payload):
    calls = []

    def _sync(*args, **kwargs):
        calls.append((args, kwargs))
        return payload

    monkeypatch.setattr(monitor_service, service_name, _sync)

    response = _request(method, path)

    assert response.status_code == 200
    assert response.json() == payload
    assert calls


def test_monitor_lease_cleanup_route_bridges_to_canonical_sandbox_cleanup(monkeypatch):
    class _Repo:
        def query_sandboxes(self):
            return [{"sandbox_id": "sandbox-1", "lease_id": "lease-1"}]

        def close(self):
            return None

    calls: list[str] = []

    monkeypatch.setattr(monitor, "make_sandbox_monitor_repo", lambda: _Repo())
    monkeypatch.setattr(
        monitor_service,
        "request_monitor_sandbox_cleanup",
        lambda sandbox_id: calls.append(sandbox_id) or {"accepted": True},
    )
    monkeypatch.setattr(
        monitor_service,
        "request_monitor_lease_cleanup",
        lambda _lease_id: (_ for _ in ()).throw(AssertionError("lease cleanup route should bridge to canonical sandbox cleanup")),
    )

    response = _request("post", "/api/monitor/leases/lease-1/cleanup")

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert calls == ["sandbox-1"]


def test_monitor_threads_routes_use_authenticated_owner(monkeypatch):
    expected = {"threads": [{"thread_id": "thread-1", "agent_user_id": "agent-1"}]}
    calls = []

    def _list_threads(app, user_id):
        calls.append((app, user_id))
        return expected

    monkeypatch.setattr(monitor_service, "list_monitor_threads", _list_threads)
    app = _app()
    app.dependency_overrides[monitor.get_current_user_id] = lambda: "owner-1"

    response = _request("get", "/api/monitor/threads", app=app)

    assert response.status_code == 200
    assert response.json() == expected
    assert calls[0][1] == "owner-1"


def test_monitor_thread_detail_route_awaits_service(monkeypatch):
    async def _detail(app, thread_id):
        return {"thread": {"thread_id": thread_id}, "trajectory": {"events": []}}

    monkeypatch.setattr(monitor_service, "get_monitor_thread_detail", _detail)

    response = _request("get", "/api/monitor/threads/thread-1")

    assert response.status_code == 200
    assert response.json()["thread"]["thread_id"] == "thread-1"


@pytest.mark.parametrize(
    ("path", "service_name", "message"),
    [
        ("/api/monitor/providers/missing", "get_monitor_provider_detail", "Provider not found: missing"),
        ("/api/monitor/leases/missing", "get_monitor_lease_detail", "Lease not found: missing"),
        ("/api/monitor/sandboxes/missing", "get_monitor_sandbox_detail", "Sandbox not found: missing"),
        ("/api/monitor/operations/missing", "get_monitor_operation_detail", "Operation not found: missing"),
        ("/api/monitor/runtimes/missing", "get_monitor_runtime_detail", "Runtime not found: missing"),
        ("/api/monitor/evaluation/batches/missing", "get_monitor_evaluation_batch_detail", "Evaluation batch not found: missing"),
        ("/api/monitor/evaluation/runs/missing", "get_monitor_evaluation_run_detail", "Evaluation run not found: missing"),
    ],
)
def test_monitor_detail_routes_map_missing_rows_to_404(monkeypatch, path, service_name, message):
    def _raise(*_args, **_kwargs):
        raise KeyError(message)

    monkeypatch.setattr(monitor_service, service_name, _raise)

    response = _request("get", path, raise_server_exceptions=False)

    assert response.status_code == 404
    assert message in response.text


def test_monitor_evaluation_batch_create_and_start_pass_request_context(monkeypatch):
    create_calls = []
    start_calls = []
    monkeypatch.setattr(
        monitor_service,
        "create_monitor_evaluation_batch",
        lambda **kwargs: create_calls.append(kwargs) or {"batch": {"batch_id": "batch-1"}},
    )
    monkeypatch.setattr(
        monitor_service,
        "start_monitor_evaluation_batch",
        lambda **kwargs: start_calls.append(kwargs) or {"accepted": True},
    )
    app = _app()
    app.dependency_overrides[get_current_user_id] = lambda: "owner-1"

    with TestClient(app) as client:
        create = client.post(
            "/api/monitor/evaluation/batches",
            json={"agent_user_id": "agent-1", "scenario_ids": ["scenario-1"], "sandbox": "local", "max_concurrent": 1},
        )
        start = client.post("/api/monitor/evaluation/batches/batch-1/start", headers={"Authorization": "Bearer token-1"})

    assert create.status_code == 200
    assert start.status_code == 200
    assert create_calls == [
        {
            "submitted_by_user_id": "owner-1",
            "agent_user_id": "agent-1",
            "scenario_ids": ["scenario-1"],
            "sandbox": "local",
            "max_concurrent": 1,
        }
    ]
    assert start_calls[0]["batch_id"] == "batch-1"
    assert start_calls[0]["base_url"] == "http://testserver"
    assert start_calls[0]["token"] == "token-1"


@pytest.mark.parametrize(
    ("verb", "path", "service_name"),
    [
        ("get", "/api/monitor/sandboxes/sandbox-1/browse", "browse_sandbox"),
        ("get", "/api/monitor/sandboxes/sandbox-1/read?path=/README.md", "read_sandbox"),
    ],
)
def test_monitor_sandbox_routes_map_runtime_failures_to_503(monkeypatch, verb, path, service_name):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(resource_service, service_name, _raise)

    response = _request(verb, path, raise_server_exceptions=False)

    assert response.status_code == 503
    assert "provider unavailable" in response.text


@pytest.mark.parametrize(
    ("path", "service_name", "expected_args"),
    [
        ("/api/monitor/sandboxes/sandbox-1/browse?path=/workspace", "browse_sandbox", ("sandbox-1", "/workspace")),
        ("/api/monitor/sandboxes/sandbox-1/read?path=/README.md", "read_sandbox", ("sandbox-1", "/README.md")),
    ],
)
def test_monitor_sandbox_routes_use_sandbox_shaped_path_subject(monkeypatch, path, service_name, expected_args):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        resource_service,
        service_name,
        lambda sandbox_id, value: calls.append((sandbox_id, value)) or {"ok": True},
    )

    response = _request("get", path)

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert calls == [expected_args]
