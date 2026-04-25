from config.loader import AgentLoader


def test_load_has_no_runtime_skill_config(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    expected_path = tmp_path / ".leon" / "skills"
    assert not expected_path.exists()

    settings = AgentLoader().load()

    assert not expected_path.exists()
    assert not hasattr(settings, "skills")


def test_runtime_skill_config_key_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    project_root = tmp_path / "project"
    runtime_dir = project_root / ".leon"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "runtime.json").write_text('{"skills": {"paths": []}}', encoding="utf-8")

    try:
        AgentLoader(project_root).load()
    except ValueError as exc:
        assert "runtime.json must not define top-level 'skills'" in str(exc)
    else:
        raise AssertionError("AgentLoader accepted removed runtime skills config")
