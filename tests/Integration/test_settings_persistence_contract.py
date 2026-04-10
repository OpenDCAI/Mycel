from __future__ import annotations

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


def test_get_settings_route_prefers_repo_backed_workspace_and_models(monkeypatch):
    repo = _FakeSettingsRepo()
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    monkeypatch.setattr(
        settings_router,
        "_load_merged_models_for_storage",
        lambda _repo, _user_id: SimpleNamespace(
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


def test_get_settings_route_does_not_import_preferences_when_repo_row_missing(monkeypatch):
    repo = _FakeSettingsRepo()
    repo.workspace_row = None
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    monkeypatch.setattr(
        settings_router,
        "_load_merged_models_for_storage",
        lambda _repo, _user_id: SimpleNamespace(
            mapping={},
            providers={},
            pool=SimpleNamespace(enabled=[], custom=[]),
        ),
    )

    with TestClient(_settings_test_app(repo)) as client:
        response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["default_workspace"] is None
    assert response.json()["recent_workspaces"] == []
    assert response.json()["default_model"] == "leon:large"


def test_get_settings_route_requires_repo_backed_storage_contract(monkeypatch):
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")

    with pytest.raises(RuntimeError, match="user_settings_repo"):
        with TestClient(_settings_test_app(None)) as client:
            client.get("/api/settings")


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
    with TestClient(_settings_test_app(repo)) as client:
        response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["enabled_models"] == ["repo-model"]
    assert response.json()["custom_models"] == ["repo-custom"]
    assert response.json()["custom_config"] == {"repo-custom": {"based_on": "gpt-4o"}}
    assert response.json()["providers"] == {"openai": {"api_key": "repo-key", "base_url": "https://repo.example"}}


def test_get_available_models_route_prefers_repo_backed_model_pool(monkeypatch):
    repo = _FakeSettingsRepo()
    repo.models_config = {
        "pool": {
            "enabled": ["repo-custom"],
            "custom": ["repo-custom"],
            "custom_providers": {"repo-custom": "openai"},
        }
    }
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    monkeypatch.setattr(
        settings_router,
        "_load_merged_models_for_storage",
        lambda _repo, _user_id: SimpleNamespace(
            pool=SimpleNamespace(enabled=["repo-custom"], custom=["repo-custom"]),
            virtual_models=[],
        ),
    )

    with TestClient(_settings_test_app(repo)) as client:
        response = client.get("/api/settings/available-models")

    assert response.status_code == 200
    model_ids = {item["id"] for item in response.json()["models"]}
    assert "repo-custom" in model_ids
    assert "fs-custom" not in model_ids


def test_test_model_route_prefers_repo_backed_provider_config(monkeypatch):
    repo = _FakeSettingsRepo()
    repo.models_config = {
        "providers": {"openai": {"api_key": "repo-key", "base_url": "https://repo.example"}},
        "pool": {"custom_providers": {"repo-custom": "openai"}},
    }
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")
    monkeypatch.setattr(
        settings_router,
        "_load_merged_models_for_storage",
        lambda _repo, _user_id: SimpleNamespace(
            active=SimpleNamespace(provider=None),
            resolve_model=lambda _model_id: ("repo-custom", {}),
            get_provider=lambda _provider_name: SimpleNamespace(api_key="repo-key", base_url="https://repo.example"),
        ),
    )
    monkeypatch.setattr("core.model_params.normalize_model_kwargs", lambda _resolved, kwargs: kwargs)

    captured: dict[str, object] = {}

    class _FakeModel:
        async def ainvoke(self, _prompt):
            return SimpleNamespace(content="ok")

    def _fake_init_chat_model(model_name: str, **kwargs):
        captured["model"] = model_name
        captured["kwargs"] = kwargs
        return _FakeModel()

    monkeypatch.setattr("langchain.chat_models.init_chat_model", _fake_init_chat_model)

    with TestClient(_settings_test_app(repo)) as client:
        response = client.post("/api/settings/models/test", json={"model_id": "repo-custom"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured["model"] == "repo-custom"
    assert captured["kwargs"] == {
        "model_provider": "openai",
        "api_key": "repo-key",
        "base_url": "https://repo.example/v1",
    }


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


def test_update_observation_settings_route_requires_repo_backed_storage_contract(monkeypatch):
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")

    with pytest.raises(RuntimeError, match="user_settings_repo"):
        with TestClient(_settings_test_app(None)) as client:
            client.post("/api/settings/observation", json={"active": "langsmith"})


@pytest.mark.asyncio
async def test_list_sandbox_configs_does_not_import_filesystem_when_repo_row_missing(
    monkeypatch,
):
    req = _request(_FakeSettingsRepo())
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")

    result = await settings_router.list_sandbox_configs(req)

    assert result == {"sandboxes": {}}


def test_update_observation_settings_route_does_not_import_filesystem_when_repo_row_missing(monkeypatch):
    repo = _FakeSettingsRepo()
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")

    with TestClient(_settings_test_app(repo)) as client:
        response = client.post("/api/settings/observation", json={"active": "langsmith"})

    assert response.status_code == 200
    assert response.json() == {"success": True, "active": "langsmith"}
    assert repo.saved_observation == {"active": "langsmith"}


def test_save_sandbox_config_route_does_not_import_filesystem_when_repo_row_missing(
    monkeypatch,
):
    repo = _FakeSettingsRepo()
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _request: "user-1")

    with TestClient(_settings_test_app(repo)) as client:
        response = client.post(
            "/api/settings/sandboxes",
            json={"name": "beta", "config": {"provider": "local"}},
        )

    assert response.status_code == 200
    assert response.json() == {"success": True, "path": "supabase://user_settings/user-1/sandbox_configs/beta"}
    assert repo.saved_sandboxes["beta"]["provider"] == "local"
    assert repo.saved_sandboxes["beta"]["name"] == "local"
    assert repo.saved_sandboxes["beta"]["on_exit"] == "pause"
