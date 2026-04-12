from pathlib import Path

from backend.web.core import config


def test_local_workspace_root_defaults_to_user_home() -> None:
    assert config.LOCAL_WORKSPACE_ROOT == Path.home().resolve()
