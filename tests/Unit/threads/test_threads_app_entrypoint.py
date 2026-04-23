import importlib

from fastapi.middleware.cors import CORSMiddleware

from backend.bootstrap import app_entrypoint


def test_threads_app_module_path_is_internalized():
    threads_app_main = importlib.import_module("backend.threads.app.main")
    assert threads_app_main.__name__ == "backend.threads.app.main"


def test_threads_app_mounts_threads_routes_only():
    threads_app_main = importlib.import_module("backend.threads.app.main")
    paths = {route.path for route in threads_app_main.app.routes}

    assert "/api/threads" in paths
    assert "/api/threads/{thread_id}/messages" in paths
    assert "/api/threads/{thread_id}/runtime" in paths


def test_threads_app_resolve_port_prefers_threads_backend_env(monkeypatch):
    threads_app_main = importlib.import_module("backend.threads.app.main")
    monkeypatch.setenv("LEON_THREADS_BACKEND_PORT", "55419")
    monkeypatch.setenv("PORT", "9000")

    assert threads_app_main._resolve_port() == 55419


def test_threads_app_resolve_port_uses_worktree_config_when_env_missing(monkeypatch):
    threads_app_main = importlib.import_module("backend.threads.app.main")
    monkeypatch.delenv("LEON_THREADS_BACKEND_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    monkeypatch.setattr(
        app_entrypoint.subprocess,
        "run",
        lambda *_args, **_kwargs: __import__("subprocess").CompletedProcess(
            args=["git", "config"],
            returncode=0,
            stdout="55420\n",
            stderr="",
        ),
    )

    assert threads_app_main._resolve_port() == 55420


def test_threads_app_includes_permissive_cors_middleware():
    threads_app_main = importlib.import_module("backend.threads.app.main")
    assert any(middleware.cls is CORSMiddleware for middleware in threads_app_main.app.user_middleware)
