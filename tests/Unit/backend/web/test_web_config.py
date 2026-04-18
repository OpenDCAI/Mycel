from pathlib import Path

from backend.web.core import config


def test_local_workspace_root_defaults_to_user_home() -> None:
    assert config.LOCAL_WORKSPACE_ROOT == Path.home().resolve()


def test_db_path_comment_does_not_label_current_sqlite_default_as_removed() -> None:
    source = Path(config.__file__).read_text()
    removed_db_path_token = "Leg" + "acy DB_PATH"

    assert removed_db_path_token not in source
