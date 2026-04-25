from config.loader import AgentLoader
from config.schema import SkillsConfig


def test_load_has_no_default_home_skill_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    expected_path = tmp_path / ".leon" / "skills"
    assert not expected_path.exists()

    settings = AgentLoader().load()

    assert not expected_path.exists()
    assert settings.skills.paths == []


def test_skills_config_allows_declared_paths_that_do_not_exist(tmp_path):
    missing_path = tmp_path / "missing-skills"

    config = SkillsConfig(paths=[str(missing_path)])

    assert config.paths == [str(missing_path)]
    assert not missing_path.exists()
