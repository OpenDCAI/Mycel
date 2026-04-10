from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.web.routers import settings as settings_router


class _FakeSettingsRepo:
    def __init__(self) -> None:
        self.workspace_row = {
            "default_workspace": "/repo/ws",
            "recent_workspaces": ["/repo/ws", "/repo/alt"],
            "default_model": "openai:gpt-5.4",
        }
        self.models_config = {"pool": {"enabled": ["openai:gpt-5.4"], "custom": []}}
        self.saved_observation = None
        self.saved_sandboxes = None

    def get(self, user_id: str):
        assert user_id == "user-1"
        return self.workspace_row

    def get_models_config(self, user_id: str):
        assert user_id == "user-1"
        return self.models_config

    def get_observation_config(self, user_id: str):
        assert user_id == "user-1"
        return None

    def get_sandbox_configs(self, user_id: str):
        assert user_id == "user-1"
        return None

    def set_observation_config(self, user_id: str, config):
        assert user_id == "user-1"
        self.saved_observation = config

    def set_sandbox_configs(self, user_id: str, configs):
        assert user_id == "user-1"
        self.saved_sandboxes = configs


def _request(repo: _FakeSettingsRepo | None):
    state = SimpleNamespace(user_settings_repo=repo) if repo is not None else SimpleNamespace()
    return SimpleNamespace(app=SimpleNamespace(state=state))


def _settings_test_app(repo: _FakeSettingsRepo | None) -> FastAPI:
    app = FastAPI()
    app.state.user_settings_repo = repo
    app.include_router(settings_router.router)
    return app


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


def test_load_models_data_does_not_import_user_json_when_repo_row_missing(monkeypatch):
    repo = _FakeSettingsRepo()
    repo.models_config = None
    req = _request(repo)
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    monkeypatch.setattr(settings_router, "_load_user_json", lambda *_parts: {"pool": {"enabled": ["fallback"]}})

    storage = settings_router._resolve_settings_storage(req)
    data = settings_router._load_models_data(storage)

    assert data == {}


def test_get_settings_route_prefers_repo_backed_workspace_and_models(monkeypatch):
    repo = _FakeSettingsRepo()
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    monkeypatch.setattr(
        settings_router,
        "_load_merged_models_for_storage",
        lambda _storage: SimpleNamespace(
            mapping={"default": SimpleNamespace(model="openai:gpt-5.4")},
            providers={"openai": SimpleNamespace(api_key=None, base_url="https://api.openai.com")},
            pool=SimpleNamespace(enabled=["openai:gpt-5.4"], custom=[]),
        ),
    )

    with TestClient(_settings_test_app(repo)) as client:
        response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {
        "default_workspace": "/repo/ws",
        "recent_workspaces": ["/repo/ws", "/repo/alt"],
        "default_model": "openai:gpt-5.4",
        "model_mapping": {"default": "openai:gpt-5.4"},
        "enabled_models": ["openai:gpt-5.4"],
        "custom_models": [],
        "custom_config": {},
        "providers": {"openai": {"api_key": None, "base_url": "https://api.openai.com"}},
    }


def test_get_settings_route_merges_repo_backed_model_pool_over_filesystem_loader(monkeypatch):
    repo = _FakeSettingsRepo()
    repo.models_config = {
        "providers": {"openai": {"api_key": "repo-key", "base_url": "https://repo.example"}},
        "pool": {
            "enabled": ["repo-model"],
            "custom": ["repo-custom"],
            "custom_config": {"repo-custom": {"based_on": "gpt-4o"}},
        },
    }
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    monkeypatch.setattr(
        settings_router,
        "load_merged_models",
        lambda: SimpleNamespace(
            mapping={"default": SimpleNamespace(model="fs-model")},
            providers={"openai": SimpleNamespace(api_key="fs-key", base_url="https://fs.example")},
            pool=SimpleNamespace(enabled=["fs-model"], custom=["fs-custom"]),
        ),
    )

    with TestClient(_settings_test_app(repo)) as client:
        response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["enabled_models"] == ["repo-model"]
    assert response.json()["custom_models"] == ["repo-custom"]
    assert response.json()["custom_config"] == {"repo-custom": {"based_on": "gpt-4o"}}
    assert response.json()["providers"] == {"openai": {"api_key": "repo-key", "base_url": "https://repo.example"}}


@pytest.mark.asyncio
async def test_get_observation_settings_keeps_loader_fallback_when_repo_row_missing(monkeypatch):
    req = _request(_FakeSettingsRepo())
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")

    class _FakeObservationConfig:
        def model_dump(self):
            return {"active": "langfuse", "langfuse": {"public_key": "pk"}}

    class _FakeObservationLoader:
        def load(self):
            return _FakeObservationConfig()

    monkeypatch.setattr("config.observation_loader.ObservationLoader", _FakeObservationLoader)

    result = await settings_router.get_observation_settings(req)

    assert result == {"active": "langfuse", "langfuse": {"public_key": "pk"}}


@pytest.mark.asyncio
async def test_list_sandbox_configs_does_not_import_filesystem_when_repo_row_missing(
    monkeypatch,
    tmp_path: Path,
):
    req = _request(_FakeSettingsRepo())
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    sandboxes_dir = tmp_path / "sandboxes"
    sandboxes_dir.mkdir()
    (sandboxes_dir / "alpha.json").write_text(json.dumps({"provider": "local"}), encoding="utf-8")
    monkeypatch.setattr(settings_router, "user_home_read_candidates", lambda *_parts: [sandboxes_dir])

    result = await settings_router.list_sandbox_configs(req)

    assert result == {"sandboxes": {}}


@pytest.mark.asyncio
async def test_update_observation_settings_does_not_import_filesystem_when_repo_row_missing(monkeypatch):
    repo = _FakeSettingsRepo()
    req = _request(repo)
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    monkeypatch.setattr(
        settings_router,
        "_load_user_json",
        lambda *_parts: {"active": "legacy", "langfuse": {"public_key": "legacy-pk"}},
    )

    result = await settings_router.update_observation_settings(
        settings_router.ObservationRequest(active="langsmith"),
        req,
    )

    assert result == {"success": True, "active": "langsmith"}
    assert repo.saved_observation == {"active": "langsmith"}


def test_update_observation_settings_route_does_not_import_filesystem_when_repo_row_missing(monkeypatch):
    repo = _FakeSettingsRepo()
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    monkeypatch.setattr(
        settings_router,
        "_load_user_json",
        lambda *_parts: {"active": "legacy", "langfuse": {"public_key": "legacy-pk"}},
    )

    with TestClient(_settings_test_app(repo)) as client:
        response = client.post("/api/settings/observation", json={"active": "langsmith"})

    assert response.status_code == 200
    assert response.json() == {"success": True, "active": "langsmith"}
    assert repo.saved_observation == {"active": "langsmith"}


@pytest.mark.asyncio
async def test_save_sandbox_config_does_not_import_filesystem_when_repo_row_missing(
    monkeypatch,
    tmp_path: Path,
):
    repo = _FakeSettingsRepo()
    req = _request(repo)
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    sandboxes_dir = tmp_path / "sandboxes"
    sandboxes_dir.mkdir()
    (sandboxes_dir / "alpha.json").write_text(json.dumps({"provider": "local"}), encoding="utf-8")
    monkeypatch.setattr(settings_router, "user_home_read_candidates", lambda *_parts: [sandboxes_dir])

    result = await settings_router.save_sandbox_config(
        settings_router.SandboxConfigRequest(name="beta", config={"provider": "local"}),
        req,
    )

    assert result == {"success": True, "path": "supabase://user_settings/user-1/sandbox_configs/beta"}
    assert "alpha" not in repo.saved_sandboxes
    assert repo.saved_sandboxes["beta"]["provider"] == "local"
    assert repo.saved_sandboxes["beta"]["name"] == "local"
    assert repo.saved_sandboxes["beta"]["on_exit"] == "pause"


def test_save_sandbox_config_route_does_not_import_filesystem_when_repo_row_missing(
    monkeypatch,
    tmp_path: Path,
):
    repo = _FakeSettingsRepo()
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    sandboxes_dir = tmp_path / "sandboxes"
    sandboxes_dir.mkdir()
    (sandboxes_dir / "alpha.json").write_text(json.dumps({"provider": "local"}), encoding="utf-8")
    monkeypatch.setattr(settings_router, "user_home_read_candidates", lambda *_parts: [sandboxes_dir])

    with TestClient(_settings_test_app(repo)) as client:
        response = client.post(
            "/api/settings/sandboxes",
            json={"name": "beta", "config": {"provider": "local"}},
        )

    assert response.status_code == 200
    assert response.json() == {"success": True, "path": "supabase://user_settings/user-1/sandbox_configs/beta"}
    assert "alpha" not in repo.saved_sandboxes
    assert repo.saved_sandboxes["beta"]["provider"] == "local"
    assert repo.saved_sandboxes["beta"]["name"] == "local"
    assert repo.saved_sandboxes["beta"]["on_exit"] == "pause"
