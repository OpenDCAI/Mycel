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
        self.account_resource_limits = None

    def get(self, user_id: str):
        assert user_id == "user-1"
        return self.workspace_row

    def get_models_config(self, user_id: str):
        assert user_id == "user-1"
        return self.models_config

    def set_models_config(self, user_id: str, models_config: dict):
        assert user_id == "user-1"
        self.models_config = models_config

    def get_account_resource_limits(self, user_id: str):
        assert user_id == "user-1"
        return self.account_resource_limits


def _settings_test_app(repo: _FakeSettingsRepo | None) -> FastAPI:
    app = FastAPI()
    app.state.user_settings_repo = repo
    app.dependency_overrides[settings_router.get_current_user_id] = lambda: "user-1"
    app.include_router(settings_router.router)
    return app


def test_get_settings_route_prefers_repo_backed_workspace_and_models(monkeypatch):
    repo = _FakeSettingsRepo()
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
        "providers": {
            "openai": {
                "api_key": None,
                "has_api_key": False,
                "credential_source": "platform",
                "base_url": "https://api.openai.com",
            }
        },
    }


def test_get_settings_route_does_not_import_preferences_when_repo_row_missing(monkeypatch):
    repo = _FakeSettingsRepo()
    repo.workspace_row = None
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


def test_get_settings_route_requires_repo_backed_storage_contract():
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
    with TestClient(_settings_test_app(repo)) as client:
        response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["enabled_models"] == ["repo-model"]
    assert response.json()["custom_models"] == ["repo-custom"]
    assert response.json()["custom_config"] == {"repo-custom": {"based_on": "gpt-4o"}}
    assert response.json()["providers"] == {
        "openai": {
            "api_key": None,
            "has_api_key": True,
            "credential_source": "user",
            "base_url": "https://repo.example",
        }
    }


def test_get_settings_route_exposes_platform_credential_source_without_user_key(monkeypatch):
    repo = _FakeSettingsRepo()
    repo.models_config = {
        "providers": {"anthropic": {"credential_source": "platform", "base_url": "https://platform.example"}},
        "pool": {"enabled": ["repo-model"], "custom": []},
    }

    with TestClient(_settings_test_app(repo)) as client:
        response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["providers"]["anthropic"] == {
        "api_key": None,
        "has_api_key": False,
        "credential_source": "platform",
        "base_url": "https://platform.example",
    }


def test_update_provider_rejects_user_credential_source_without_key():
    repo = _FakeSettingsRepo()

    with TestClient(_settings_test_app(repo)) as client:
        response = client.post(
            "/api/settings/providers",
            json={"provider": "openai", "credential_source": "user", "api_key": None, "base_url": None},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "User credential source requires an API key"
    assert repo.models_config == {"pool": {"enabled": ["openai:gpt-5.4"], "custom": []}}


def test_update_provider_preserves_existing_key_when_base_url_changes():
    repo = _FakeSettingsRepo()
    repo.models_config = {
        "providers": {"openai": {"credential_source": "user", "api_key": "repo-key", "base_url": "https://old.example"}},
        "pool": {"enabled": ["repo-model"], "custom": []},
    }

    with TestClient(_settings_test_app(repo)) as client:
        response = client.post(
            "/api/settings/providers",
            json={"provider": "openai", "api_key": None, "base_url": None},
        )

    assert response.status_code == 200
    assert repo.models_config["providers"]["openai"] == {"credential_source": "user", "api_key": "repo-key"}


def test_update_provider_platform_source_removes_stored_user_key():
    repo = _FakeSettingsRepo()
    repo.models_config = {
        "providers": {"openai": {"credential_source": "user", "api_key": "repo-key", "base_url": "https://old.example"}},
        "pool": {"enabled": ["repo-model"], "custom": []},
    }

    with TestClient(_settings_test_app(repo)) as client:
        response = client.post(
            "/api/settings/providers",
            json={"provider": "openai", "credential_source": "platform", "api_key": None, "base_url": None},
        )

    assert response.status_code == 200
    assert repo.models_config["providers"]["openai"] == {"credential_source": "platform"}


def test_account_resources_route_returns_backend_quota_contract(monkeypatch):
    app = _settings_test_app(_FakeSettingsRepo())
    app.state.thread_repo = object()
    app.state._supabase_client = object()
    seen: dict[str, object] = {}

    def _fake_count_user_visible_leases_by_provider(user_id: str, **kwargs):
        seen["user_id"] = user_id
        seen["kwargs"] = kwargs
        return {"local": 1, "daytona_selfhost": 2, "e2b": 1}

    monkeypatch.setattr(
        settings_router.account_resource_service.sandbox_service,
        "count_user_visible_leases_by_provider",
        _fake_count_user_visible_leases_by_provider,
    )

    with TestClient(app) as client:
        response = client.get("/api/settings/account-resources")

    assert response.status_code == 200
    items = {item["provider_name"]: item for item in response.json()["items"]}
    assert items["local"] == {
        "resource": "sandbox",
        "provider_name": "local",
        "label": "Local",
        "limit": 999,
        "used": 1,
        "remaining": 998,
        "can_create": True,
    }
    assert items["daytona_selfhost"]["limit"] == 2
    assert items["daytona_selfhost"]["used"] == 2
    assert items["daytona_selfhost"]["remaining"] == 0
    assert items["daytona_selfhost"]["can_create"] is False
    assert items["e2b"]["limit"] == 0
    assert items["e2b"]["used"] == 1
    assert items["e2b"]["can_create"] is False
    assert items["platform_tokens"] == {
        "resource": "token",
        "provider_name": "platform_tokens",
        "label": "平台 Token",
        "limit": 100_000_000,
        "used": 0,
        "remaining": 100_000_000,
        "can_create": True,
        "period": "weekly",
        "unit": "tokens",
    }
    assert seen == {
        "user_id": "user-1",
        "kwargs": {"thread_repo": app.state.thread_repo, "supabase_client": app.state._supabase_client},
    }


def test_account_resources_route_applies_user_limit_overrides(monkeypatch):
    repo = _FakeSettingsRepo()
    repo.account_resource_limits = {"sandbox": {"daytona_selfhost": 5, "docker": 3}, "token": {"weekly": 50_000_000}}
    app = _settings_test_app(repo)
    app.state.thread_repo = object()

    def _fake_count_user_visible_leases_by_provider(user_id: str, **kwargs):
        assert user_id == "user-1"
        assert kwargs == {"thread_repo": app.state.thread_repo}
        return {"daytona_selfhost": 2}

    monkeypatch.setattr(
        settings_router.account_resource_service.sandbox_service,
        "count_user_visible_leases_by_provider",
        _fake_count_user_visible_leases_by_provider,
    )

    with TestClient(app) as client:
        response = client.get("/api/settings/account-resources")

    assert response.status_code == 200
    items = {item["provider_name"]: item for item in response.json()["items"]}
    assert items["daytona_selfhost"]["limit"] == 5
    assert items["daytona_selfhost"]["used"] == 2
    assert items["daytona_selfhost"]["remaining"] == 3
    assert items["daytona_selfhost"]["can_create"] is True
    assert items["docker"]["limit"] == 3
    assert items["docker"]["used"] == 0
    assert items["docker"]["remaining"] == 3
    assert items["docker"]["can_create"] is True
    assert items["platform_tokens"]["limit"] == 50_000_000
    assert items["platform_tokens"]["remaining"] == 50_000_000


def test_app_settings_router_does_not_expose_monitor_owned_surfaces():
    app = _settings_test_app(_FakeSettingsRepo())

    with TestClient(app) as client:
        paths = set(client.get("/openapi.json").json()["paths"])

    assert "/api/settings/account-resources" in paths
    assert "/api/settings/observation" not in paths
    assert "/api/settings/observation/verify" not in paths
    assert "/api/settings/sandboxes" not in paths


def test_get_available_models_route_prefers_repo_backed_model_pool(monkeypatch):
    repo = _FakeSettingsRepo()
    repo.models_config = {
        "pool": {
            "enabled": ["repo-custom"],
            "custom": ["repo-custom"],
            "custom_providers": {"repo-custom": "openai"},
        }
    }
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
    monkeypatch.setattr(
        settings_router,
        "_load_merged_models_for_storage",
        lambda _repo, _user_id: SimpleNamespace(
            active=SimpleNamespace(provider=None),
            resolve_model=lambda _model_id: ("repo-custom", {}),
            get_provider=lambda _provider_name: SimpleNamespace(api_key="repo-key", base_url="https://repo.example"),
            resolve_api_key=lambda _provider_name: "repo-key",
            resolve_base_url=lambda _provider_name: "https://repo.example",
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


def test_test_model_route_uses_platform_base_url_when_provider_row_missing(monkeypatch):
    repo = _FakeSettingsRepo()
    repo.models_config = {}
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://anthropic.example")
    monkeypatch.setenv("OPENAI_API_KEY", "platform-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://platform.example")

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
        response = client.post("/api/settings/models/test", json={"model_id": "openai:gpt-4o"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured["model"] == "gpt-4o"
    assert captured["kwargs"] == {
        "model_provider": "openai",
        "api_key": "platform-key",
        "base_url": "https://platform.example/v1",
    }
