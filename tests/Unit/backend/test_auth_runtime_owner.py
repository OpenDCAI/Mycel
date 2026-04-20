import inspect

from backend import auth_runtime_bootstrap, avatar_files, avatar_urls, contact_bootstrap, recipe_bootstrap
from backend import auth_service as neutral_auth_service
from backend.auth_service import AuthService
from backend.web.models import panel as panel_models
from backend.web.routers import marketplace as marketplace_router
from backend.web.routers import panel as panel_router
from backend.web.routers import users as users_router
from backend.web.services import agent_user_service, library_service


def test_auth_runtime_bootstrap_depends_on_neutral_auth_service():
    source = inspect.getsource(auth_runtime_bootstrap)

    assert "backend.web.services.auth_service" not in source
    assert "backend.auth_service" in source


def test_web_auth_service_is_compat_shell():
    assert AuthService is neutral_auth_service.AuthService


def test_neutral_auth_service_uses_neutral_avatar_file_owner():
    source = inspect.getsource(neutral_auth_service)

    assert "backend.web.routers.users" not in source
    assert "backend.avatar_files" in source


def test_users_router_keeps_avatar_processing_compat_surface():
    assert users_router.process_and_save_avatar is avatar_files.process_and_save_avatar


def test_neutral_auth_service_uses_neutral_contact_bootstrap_owner():
    source = inspect.getsource(neutral_auth_service)

    assert "backend.web.services.contact_bootstrap_service" not in source
    assert "backend.contact_bootstrap" in source


def test_agent_user_service_uses_neutral_contact_bootstrap_owner():
    source = inspect.getsource(agent_user_service)

    assert "backend.web.services.contact_bootstrap_service" not in source
    assert "backend.contact_bootstrap" in source


def test_contact_bootstrap_owner_exports_contact_bootstrap_entrypoint() -> None:
    assert contact_bootstrap.ensure_owner_agent_contact is not None


def test_neutral_auth_service_uses_neutral_recipe_bootstrap_owner():
    source = inspect.getsource(neutral_auth_service)

    assert "backend.web.services import library_service" not in source
    assert "backend.recipe_bootstrap" in source


def test_web_library_service_keeps_recipe_bootstrap_compat_surface():
    assert library_service.seed_default_recipes is recipe_bootstrap.seed_default_recipes


def test_web_library_service_uses_neutral_library_path_owner() -> None:
    source = inspect.getsource(library_service)

    assert "from backend.web.core.paths import library_dir" not in source
    assert "from backend.library_paths import LIBRARY_DIR" in source


def test_agent_user_service_uses_neutral_versioning_owner() -> None:
    source = inspect.getsource(agent_user_service)

    assert "from backend.web.utils.versioning import BumpType, bump_semver" not in source
    assert "from backend.versioning import BumpType, bump_semver" in source


def test_agent_user_service_uses_neutral_snapshot_install_owner() -> None:
    source = inspect.getsource(agent_user_service)

    assert "def install_from_snapshot(" not in source
    assert "import backend.agent_user_snapshot_install as _snapshot_install_owner" in source
    assert "install_from_snapshot = _snapshot_install_owner.install_from_snapshot" in source


def test_panel_models_uses_neutral_versioning_owner() -> None:
    source = inspect.getsource(panel_models)

    assert "from backend.web.utils.versioning import BumpType" not in source
    assert "from backend.versioning import BumpType" in source


def test_neutral_avatar_helpers_use_neutral_avatar_path_owner():
    avatar_file_source = inspect.getsource(avatar_files)
    avatar_url_source = inspect.getsource(avatar_urls)

    assert "backend.web.core.paths" not in avatar_file_source
    assert "backend.web.core.paths" not in avatar_url_source
    assert "backend.avatar_paths" in avatar_file_source
    assert "backend.avatar_paths" in avatar_url_source


def test_web_paths_keeps_avatar_path_compat_surface():
    from backend import avatar_paths
    from backend.web.core import paths

    assert paths.avatars_dir is avatar_paths.avatars_dir


def test_panel_router_uses_neutral_profile_owner() -> None:
    source = inspect.getsource(panel_router)

    assert "backend.web.services import agent_user_service, library_service, profile_service" not in source
    assert "from backend import profile as profile_owner" in source


def test_marketplace_router_uses_neutral_profile_owner() -> None:
    source = inspect.getsource(marketplace_router)

    assert "from backend.web.services.profile_service import get_profile" not in source
    assert "from backend.profile import get_profile" in source
