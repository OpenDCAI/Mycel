from pathlib import Path

from config.loader import ConfigLoader


def test_load_bootstraps_default_home_skill_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    expected_path = tmp_path / ".leon" / "skills"
    assert not expected_path.exists()

    settings = ConfigLoader().load()

    assert expected_path.is_dir()
    assert Path(settings.skills.paths[0]).expanduser() == expected_path


def test_load_bootstraps_tmp_mapped_skill_dir(monkeypatch):
    tmp_home = Path("/tmp/leon-loader-mapped-home")
    skill_dir = tmp_home / ".leon" / "skills"
    if skill_dir.exists():
        import shutil
        shutil.rmtree(skill_dir.parent)

    monkeypatch.setenv("HOME", str(tmp_home))

    settings = ConfigLoader().load({
        "skills": {
            "enabled": True,
            "paths": [str(skill_dir)],
            "skills": {},
        },
    })

    assert skill_dir.is_dir()
    assert Path(settings.skills.paths[0]).expanduser() == skill_dir
