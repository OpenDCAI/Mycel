import subprocess

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend import app_entrypoint
from backend.monitor_app import lifespan as monitor_app_lifespan
from backend.monitor_app import main as monitor_app_main

app = monitor_app_main.app


def test_monitor_app_mounts_only_global_monitor_routes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(monitor_app_lifespan, "attach_runtime_storage_state", lambda _app: object())
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/api/monitor/resources" in paths
    assert "/api/monitor/sandboxes" in paths
    assert "/api/monitor/threads" not in paths
    assert "/api/monitor/threads/{thread_id}" not in paths
    assert "/api/monitor/evaluation/batches/{batch_id}/start" not in paths
    assert set(paths["/api/monitor/evaluation/batches"]) == {"get"}


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
