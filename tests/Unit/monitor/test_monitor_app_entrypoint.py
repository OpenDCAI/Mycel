import subprocess
from types import SimpleNamespace

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.bootstrap import app_entrypoint
from backend.monitor.api.http import execution_target as monitor_execution_target
from backend.monitor.app import lifespan as monitor_app_lifespan
from backend.monitor.app import main as monitor_app_main
from backend.monitor.infrastructure.web import gateway as monitor_gateway

app = monitor_app_main.app


def test_monitor_app_mounts_only_global_monitor_routes(monkeypatch: pytest.MonkeyPatch):
    monitor_storage = SimpleNamespace(
        storage_container=SimpleNamespace(user_repo=lambda: object(), contact_repo=lambda: object()),
    )
    monkeypatch.setattr(monitor_app_lifespan, "attach_runtime_storage_state", lambda _app: monitor_storage)
    monkeypatch.setattr(monitor_app_lifespan, "attach_auth_runtime_state", lambda *_args, **_kwargs: object())
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/api/monitor/resources" in paths
    assert "/api/monitor/sandboxes" in paths
    assert "/api/monitor/threads" not in paths
    assert "/api/monitor/threads/{thread_id}" not in paths
    assert "/api/monitor/evaluation/batches/{batch_id}/start" in paths
    assert set(paths["/api/monitor/evaluation/batches"]) == {"get", "post"}


def test_monitor_app_accepts_evaluation_batch_create(monkeypatch: pytest.MonkeyPatch):
    user_repo = SimpleNamespace(get_by_id=lambda user_id: {"user_id": user_id})
    monitor_storage = SimpleNamespace(
        storage_container=SimpleNamespace(user_repo=lambda: user_repo, contact_repo=lambda: object()),
    )
    monkeypatch.setattr(monitor_app_lifespan, "attach_runtime_storage_state", lambda _app: monitor_storage)
    monkeypatch.setattr(
        monitor_app_lifespan,
        "attach_auth_runtime_state",
        lambda app, *, storage_state, contact_repo: (
            setattr(
                app.state,
                "auth_runtime_state",
                SimpleNamespace(auth_service=SimpleNamespace(verify_token=lambda _token: {"user_id": "owner-1"})),
            )
            or object()
        ),
    )
    monkeypatch.setattr(
        monitor_gateway,
        "create_evaluation_batch",
        lambda **kwargs: {"batch": kwargs},
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/monitor/evaluation/batches",
            json={"agent_user_id": "agent-1", "scenario_ids": ["scenario-1"], "sandbox": "local", "max_concurrent": 1},
            headers={"Authorization": "Bearer token-1"},
        )

    assert response.status_code == 200
    payload = response.json()["batch"]
    assert payload["submitted_by_user_id"] == "owner-1"
    assert payload["agent_user_id"] == "agent-1"


def test_monitor_app_rejects_deleted_user_for_evaluation_batch_create(monkeypatch: pytest.MonkeyPatch):
    user_repo = SimpleNamespace(get_by_id=lambda _user_id: None)
    monitor_storage = SimpleNamespace(
        storage_container=SimpleNamespace(user_repo=lambda: user_repo, contact_repo=lambda: object()),
    )
    monkeypatch.setattr(monitor_app_lifespan, "attach_runtime_storage_state", lambda _app: monitor_storage)
    monkeypatch.setattr(
        monitor_app_lifespan,
        "attach_auth_runtime_state",
        lambda app, *, storage_state, contact_repo: (
            setattr(
                app.state,
                "auth_runtime_state",
                SimpleNamespace(auth_service=SimpleNamespace(verify_token=lambda _token: {"user_id": "owner-1"})),
            )
            or object()
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/monitor/evaluation/batches",
            json={"agent_user_id": "agent-1", "scenario_ids": ["scenario-1"], "sandbox": "local", "max_concurrent": 1},
            headers={"Authorization": "Bearer token-1"},
        )

    assert response.status_code == 401
    assert "User no longer exists" in response.text


def test_monitor_app_accepts_evaluation_batch_start(monkeypatch: pytest.MonkeyPatch):
    user_repo = SimpleNamespace(get_by_id=lambda user_id: {"user_id": user_id})
    monitor_storage = SimpleNamespace(
        storage_container=SimpleNamespace(user_repo=lambda: user_repo, contact_repo=lambda: object()),
    )
    monkeypatch.setattr(monitor_app_lifespan, "attach_runtime_storage_state", lambda _app: monitor_storage)
    monkeypatch.setattr(
        monitor_app_lifespan,
        "attach_auth_runtime_state",
        lambda app, *, storage_state, contact_repo: (
            setattr(
                app.state,
                "auth_runtime_state",
                SimpleNamespace(auth_service=SimpleNamespace(verify_token=lambda _token: {"user_id": "owner-1"})),
            )
            or object()
        ),
    )
    monkeypatch.setattr(
        monitor_gateway,
        "start_evaluation_batch",
        lambda **kwargs: {"batch": kwargs},
    )
    monkeypatch.setattr(
        monitor_execution_target,
        "resolve_app_port",
        lambda *_args, **_kwargs: 55417,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/monitor/evaluation/batches/batch-1/start",
            headers={"Authorization": "Bearer token-1"},
        )

    assert response.status_code == 200
    payload = response.json()["batch"]
    assert payload["batch_id"] == "batch-1"
    assert payload["execution_base_url"] == "http://127.0.0.1:55417"
    assert payload["token"] == "token-1"


def test_monitor_app_maps_missing_remote_execution_target_to_503(monkeypatch: pytest.MonkeyPatch):
    user_repo = SimpleNamespace(get_by_id=lambda user_id: {"user_id": user_id})
    monitor_storage = SimpleNamespace(
        storage_container=SimpleNamespace(user_repo=lambda: user_repo, contact_repo=lambda: object()),
    )
    monkeypatch.setattr(monitor_app_lifespan, "attach_runtime_storage_state", lambda _app: monitor_storage)
    monkeypatch.setattr(
        monitor_app_lifespan,
        "attach_auth_runtime_state",
        lambda app, *, storage_state, contact_repo: (
            setattr(
                app.state,
                "auth_runtime_state",
                SimpleNamespace(auth_service=SimpleNamespace(verify_token=lambda _token: {"user_id": "owner-1"})),
            )
            or object()
        ),
    )
    monkeypatch.delenv("LEON_MONITOR_EVALUATION_BASE_URL", raising=False)

    with TestClient(app, base_url="https://monitor.example.com", raise_server_exceptions=False) as client:
        response = client.post(
            "/api/monitor/evaluation/batches/batch-1/start",
            headers={"Authorization": "Bearer token-1"},
        )

    assert response.status_code == 503
    assert "LEON_MONITOR_EVALUATION_BASE_URL is required" in response.text


def test_monitor_app_resolve_port_prefers_monitor_backend_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEON_MONITOR_BACKEND_PORT", "55417")
    monkeypatch.setenv("PORT", "9000")

    assert app_entrypoint.resolve_app_port("LEON_MONITOR_BACKEND_PORT", "worktree.ports.monitor-backend", 8011) == 55417


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

    assert app_entrypoint.resolve_app_port("LEON_MONITOR_BACKEND_PORT", "worktree.ports.monitor-backend", 8011) == 55418


def test_monitor_app_includes_permissive_cors_middleware():
    assert any(middleware.cls is CORSMiddleware for middleware in app.user_middleware)
