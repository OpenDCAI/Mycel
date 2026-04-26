from config.loader import AgentLoader


def test_load_has_no_runtime_skill_config(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    expected_path = tmp_path / ".leon" / "skills"
    assert not expected_path.exists()

    settings = AgentLoader().load()

    assert not expected_path.exists()
    assert not hasattr(settings, "skills")


def test_cli_skill_config_key_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    try:
        AgentLoader().load(cli_overrides={"skills": {"paths": []}})
    except ValueError as exc:
        assert "runtime.json must not define top-level 'skills'" in str(exc)
    else:
        raise AssertionError("AgentLoader accepted removed runtime skills config")
