from pathlib import Path

from config.loader import ConfigLoader


def test_load_bootstraps_default_home_skill_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    expected_path = tmp_path / ".leon" / "skills"
    assert not expected_path.exists()

    settings = ConfigLoader().load()

    assert expected_path.is_dir()
    assert Path(settings.skills.paths[0]).expanduser() == expected_path
