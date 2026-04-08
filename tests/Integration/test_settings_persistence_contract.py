from __future__ import annotations

from types import SimpleNamespace

from backend.web.routers import settings as settings_router


class _FakeSettingsRepo:
    def __init__(self) -> None:
        self.workspace_row = {
            "default_workspace": "/repo/ws",
            "recent_workspaces": ["/repo/ws", "/repo/alt"],
            "default_model": "openai:gpt-5.4",
        }
        self.models_config = {"pool": {"enabled": ["openai:gpt-5.4"], "custom": []}}

    def get(self, user_id: str):
        assert user_id == "user-1"
        return self.workspace_row

    def get_models_config(self, user_id: str):
        assert user_id == "user-1"
        return self.models_config


def _request(repo: _FakeSettingsRepo | None):
    state = SimpleNamespace(user_settings_repo=repo) if repo is not None else SimpleNamespace()
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_resolve_settings_storage_marks_repo_backed(monkeypatch):
    req = _request(_FakeSettingsRepo())
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")

    storage = settings_router._resolve_settings_storage(req)

    assert storage.repo_backed is True
    assert storage.repo is req.app.state.user_settings_repo
    assert storage.user_id == "user-1"


def test_load_workspace_settings_prefers_repo_row(monkeypatch):
    req = _request(_FakeSettingsRepo())
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")

    storage = settings_router._resolve_settings_storage(req)
    settings = settings_router._load_workspace_settings(storage)

    assert settings.default_workspace == "/repo/ws"
    assert settings.recent_workspaces == ["/repo/ws", "/repo/alt"]
    assert settings.default_model == "openai:gpt-5.4"


def test_load_models_data_prefers_repo_models_config(monkeypatch):
    req = _request(_FakeSettingsRepo())
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    monkeypatch.setattr(settings_router, "_load_user_json", lambda *_parts: {"pool": {"enabled": ["fallback"]}})

    storage = settings_router._resolve_settings_storage(req)
    data = settings_router._load_models_data(storage)

    assert data == {"pool": {"enabled": ["openai:gpt-5.4"], "custom": []}}


def test_load_models_data_falls_back_to_user_json_without_repo_context(monkeypatch):
    monkeypatch.setattr(settings_router, "_load_user_json", lambda *_parts: {"pool": {"enabled": ["fallback"]}})

    storage = settings_router._resolve_settings_storage(_request(None))
    data = settings_router._load_models_data(storage)

    assert data == {"pool": {"enabled": ["fallback"]}}
