import sys
from pathlib import Path

import pytest

from config.loader import AgentLoader


@pytest.mark.skipif(sys.platform == "win32", reason="HOME monkeypatch does not affect expanduser on Windows")
def test_load_bootstraps_default_home_skill_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    expected_path = tmp_path / ".leon" / "skills"
    assert not expected_path.exists()

    settings = AgentLoader().load()

    assert expected_path.is_dir()
    assert Path(settings.skills.paths[0]).expanduser() == expected_path
