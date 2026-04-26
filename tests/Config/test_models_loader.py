import inspect
from pathlib import Path

from config.models_loader import ModelsLoader


def test_models_loader_has_no_workspace_root_source() -> None:
    signature = inspect.signature(ModelsLoader)

    assert "workspace_root" not in signature.parameters


def test_models_loader_does_not_read_user_home_models_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    user_dir = tmp_path / ".leon"
    user_dir.mkdir(parents=True)
    (user_dir / "models.json").write_text(
        '{"active":{"model":"openai:local-user-model"},"providers":{"openai":{"api_key":"local-user-key"}}}',
        encoding="utf-8",
    )

    config = ModelsLoader().load()

    assert config.active is None
    assert config.resolve_api_key("openai") is None


def test_models_loader_explicit_user_config_does_not_read_user_home_models_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    user_dir = tmp_path / ".leon"
    user_dir.mkdir(parents=True)
    (user_dir / "models.json").write_text(
        '{"providers":{"openai":{"api_key":"local-user-key"}}}',
        encoding="utf-8",
    )

    config = ModelsLoader().load_with_user_config({"providers": {"openai": {"api_key": "repo-key"}}})

    assert config.resolve_api_key("openai") == "repo-key"
