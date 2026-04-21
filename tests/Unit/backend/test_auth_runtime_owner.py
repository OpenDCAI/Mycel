from backend import auth_service as neutral_auth_service
from backend import avatar_files, avatar_urls, contact_bootstrap, recipe_bootstrap
from backend.identity.auth.service import AuthService
from backend.web.routers import users as users_router
from backend.web.services import library_service


def test_web_auth_service_is_compat_shell():
    assert AuthService is neutral_auth_service.AuthService


def test_users_router_keeps_avatar_processing_compat_surface():
    assert users_router.process_and_save_avatar is avatar_files.process_and_save_avatar


def test_contact_bootstrap_owner_exports_contact_bootstrap_entrypoint() -> None:
    assert contact_bootstrap.ensure_owner_agent_contact is not None


def test_web_library_service_keeps_recipe_bootstrap_compat_surface():
    assert library_service.seed_default_recipes is recipe_bootstrap.seed_default_recipes


def test_neutral_avatar_helpers_use_neutral_avatar_path_owner():
    assert avatar_files.process_and_save_avatar is not None
    assert avatar_urls.avatar_url is not None


def test_web_paths_keeps_avatar_path_compat_surface():
    from backend import avatar_paths
    from backend.web.core import paths

    assert paths.avatars_dir is avatar_paths.avatars_dir
