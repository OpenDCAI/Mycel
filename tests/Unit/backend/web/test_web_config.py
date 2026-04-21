from pathlib import Path

from backend.sandboxes import paths as sandbox_paths
from backend.web.core import config


def test_local_workspace_root_defaults_to_user_home() -> None:
    assert config.LOCAL_WORKSPACE_ROOT == Path.home().resolve()


def test_web_config_keeps_sandboxes_dir_compat_surface() -> None:
    assert config.SANDBOXES_DIR == sandbox_paths.SANDBOXES_DIR
