import inspect
from pathlib import Path

from config.observation_loader import ObservationLoader


def test_observation_loader_has_no_workspace_root_source() -> None:
    signature = inspect.signature(ObservationLoader)

    assert "workspace_root" not in signature.parameters


def test_observation_loader_does_not_read_user_home_observation_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    user_dir = tmp_path / ".leon"
    user_dir.mkdir(parents=True)
    (user_dir / "observation.json").write_text(
        '{"active":"langfuse","langfuse":{"secret_key":"local-secret","public_key":"local-public"}}',
        encoding="utf-8",
    )

    config = ObservationLoader().load()

    assert config.active is None
    assert config.langfuse.secret_key is None
    assert config.langfuse.public_key is None
