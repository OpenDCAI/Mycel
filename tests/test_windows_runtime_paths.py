from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _set_windows_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


def test_windows_models_loader_merges_legacy_and_runtime_user_config(monkeypatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime-root"
    _set_windows_home(monkeypatch, tmp_path)
    monkeypatch.setenv("LEON_DB_PATH", str(runtime_root / "leon.db"))

    legacy_models = tmp_path / ".leon" / "models.json"
    runtime_models = runtime_root / "models.json"
    _write_json(
        legacy_models,
        {
            "providers": {"anthropic": {"api_key": "legacy-key"}},
            "mapping": {"leon:large": {"model": "legacy-model"}},
        },
    )
    _write_json(
        runtime_models,
        {
            "providers": {"openai": {"api_key": "runtime-key"}},
            "mapping": {"leon:large": {"model": "runtime-model"}},
        },
    )

    import config.models_loader as models_loader_module

    models_loader_module = importlib.reload(models_loader_module)
    models = models_loader_module.ModelsLoader().load()

    assert models.providers["anthropic"].api_key == "legacy-key"
    assert models.providers["openai"].api_key == "runtime-key"
    assert models.mapping["leon:large"].model == "runtime-model"


def test_windows_config_loader_reads_runtime_user_config_and_members(monkeypatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime-root"
    _set_windows_home(monkeypatch, tmp_path)
    monkeypatch.setenv("LEON_DB_PATH", str(runtime_root / "leon.db"))

    _write_json(runtime_root / "runtime.json", {"runtime": {"temperature": 0.7}})
    member_dir = runtime_root / "members" / "m_runtime_member"
    member_dir.mkdir(parents=True, exist_ok=True)
    (member_dir / "agent.md").write_text(
        "---\nname: runtime-member\ndescription: runtime member\n---\n\nYou are runtime member.\n",
        encoding="utf-8",
    )

    import config.loader as loader_module

    loader_module = importlib.reload(loader_module)
    loader = loader_module.ConfigLoader()
    settings = loader.load()
    agents = loader.load_all_agents()

    assert settings.runtime.temperature == 0.7
    assert "runtime-member" in agents


def test_windows_settings_and_sandbox_paths_use_runtime_root(monkeypatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime-root"
    _set_windows_home(monkeypatch, tmp_path)
    monkeypatch.setenv("LEON_DB_PATH", str(runtime_root / "leon.db"))

    import backend.web.routers.settings as settings_module
    import sandbox.config as sandbox_config_module

    settings_module = importlib.reload(settings_module)
    sandbox_config_module = importlib.reload(sandbox_config_module)

    assert settings_module.SETTINGS_FILE == runtime_root / "preferences.json"
    assert settings_module.MODELS_FILE == runtime_root / "models.json"
    assert settings_module.OBSERVATION_FILE == runtime_root / "observation.json"
    assert settings_module.SANDBOXES_DIR == runtime_root / "sandboxes"

    saved = sandbox_config_module.SandboxConfig(provider="docker").save("win-test")
    assert saved == runtime_root / "sandboxes" / "win-test.json"
    assert sandbox_config_module.SandboxConfig.load("win-test").provider == "docker"


def test_windows_profile_wechat_and_agent_registry_use_runtime_root(monkeypatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime-root"
    _set_windows_home(monkeypatch, tmp_path)
    monkeypatch.setenv("LEON_DB_PATH", str(runtime_root / "leon.db"))

    import backend.web.services.profile_service as profile_service_module
    import backend.web.services.wechat_service as wechat_service_module
    import core.identity.agent_registry as agent_registry_module

    profile_service_module = importlib.reload(profile_service_module)
    wechat_service_module = importlib.reload(wechat_service_module)
    agent_registry_module = importlib.reload(agent_registry_module)

    assert profile_service_module.CONFIG_PATH == runtime_root / "config.json"
    assert wechat_service_module.CONNECTIONS_BASE == runtime_root / "connections" / "wechat"
    assert agent_registry_module.INSTANCES_FILE == runtime_root / "agent_instances.json"


def test_windows_misc_runtime_db_adjacent_paths_use_runtime_root(monkeypatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime-root"
    _set_windows_home(monkeypatch, tmp_path)
    monkeypatch.setenv("LEON_DB_PATH", str(runtime_root / "leon.db"))

    import core.agents.registry as agents_registry_module
    import core.runtime.middleware.monitor.cost as cost_module

    agents_registry_module = importlib.reload(agents_registry_module)
    cost_module = importlib.reload(cost_module)

    assert agents_registry_module.AgentRegistry.DEFAULT_DB_PATH == runtime_root / "agent_registry.db"
    assert cost_module._CACHE_PATH == runtime_root / "pricing_cache.json"
