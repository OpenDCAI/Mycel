import subprocess

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.bootstrap import app_entrypoint
from backend.monitor.api.http.dependencies import get_current_user_id
from backend.monitor.app import lifespan as monitor_app_lifespan
from backend.monitor.app import main as monitor_app_main
from backend.monitor.infrastructure.web import gateway as monitor_gateway

app = monitor_app_main.app


def test_monitor_app_module_path_is_internalized():
    assert monitor_app_main.__name__ == "backend.monitor.app.main"


def test_monitor_app_mounts_only_global_monitor_routes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(monitor_app_lifespan, "attach_runtime_storage_state", lambda _app: object())
    monkeypatch.setattr(monitor_app_lifespan, "attach_auth_runtime_state", lambda *_args, **_kwargs: object())
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/api/monitor/resources" in paths
    assert "/api/monitor/sandboxes" in paths
    assert "/api/monitor/threads" not in paths
    assert "/api/monitor/threads/{thread_id}" not in paths
    assert "/api/monitor/evaluation/batches/{batch_id}/start" not in paths
    assert set(paths["/api/monitor/evaluation/batches"]) == {"get", "post"}


def test_monitor_app_accepts_evaluation_batch_create(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(monitor_app_lifespan, "attach_runtime_storage_state", lambda _app: object())
    monkeypatch.setattr(monitor_app_lifespan, "attach_auth_runtime_state", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        monitor_gateway,
        "create_evaluation_batch",
        lambda **kwargs: {"batch": kwargs},
    )
    app.dependency_overrides[get_current_user_id] = lambda: "owner-1"
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/monitor/evaluation/batches",
                json={"agent_user_id": "agent-1", "scenario_ids": ["scenario-1"], "sandbox": "local", "max_concurrent": 1},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["batch"]
    assert payload["submitted_by_user_id"] == "owner-1"
    assert payload["agent_user_id"] == "agent-1"


def test_monitor_app_resolve_port_prefers_monitor_backend_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEON_MONITOR_BACKEND_PORT", "55417")
    monkeypatch.setenv("PORT", "9000")

    assert monitor_app_main._resolve_port() == 55417


def test_monitor_app_resolve_port_uses_worktree_config_when_env_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LEON_MONITOR_BACKEND_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    def _run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["git", "config"],
            returncode=0,
            stdout="55418\n",
            stderr="",
        )

    monkeypatch.setattr(app_entrypoint.subprocess, "run", _run)

    assert monitor_app_main._resolve_port() == 55418


def test_monitor_app_includes_permissive_cors_middleware():
    assert any(middleware.cls is CORSMiddleware for middleware in app.user_middleware)
