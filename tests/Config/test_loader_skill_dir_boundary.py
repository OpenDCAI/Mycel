import sys
from pathlib import Path

import pytest

from config.loader import AgentLoader
from config.schema import SkillsConfig


@pytest.mark.skipif(sys.platform == "win32", reason="HOME monkeypatch does not affect expanduser on Windows")
def test_load_does_not_create_default_home_skill_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    expected_path = tmp_path / ".leon" / "skills"
    assert not expected_path.exists()

    settings = AgentLoader().load()

    assert not expected_path.exists()
    assert Path(settings.skills.paths[0]).expanduser() == expected_path


def test_skills_config_allows_declared_paths_that_do_not_exist(tmp_path):
    missing_path = tmp_path / "missing-skills"

    config = SkillsConfig(paths=[str(missing_path)])

    assert config.paths == [str(missing_path)]
    assert not missing_path.exists()
