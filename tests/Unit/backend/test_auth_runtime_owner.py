import inspect

from backend import auth_runtime_bootstrap, avatar_files, contact_bootstrap, recipe_bootstrap
from backend import auth_service as neutral_auth_service
from backend.web.routers import users as users_router
from backend.web.services import agent_user_service, library_service
from backend.web.services.auth_service import AuthService


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


def test_web_contact_bootstrap_service_is_compat_shell():
    from backend.web.services import contact_bootstrap_service

    assert contact_bootstrap_service.ensure_owner_agent_contact is contact_bootstrap.ensure_owner_agent_contact


def test_neutral_auth_service_uses_neutral_recipe_bootstrap_owner():
    source = inspect.getsource(neutral_auth_service)

    assert "backend.web.services import library_service" not in source
    assert "backend.recipe_bootstrap" in source


def test_web_library_service_keeps_recipe_bootstrap_compat_surface():
    assert library_service.seed_default_recipes is recipe_bootstrap.seed_default_recipes
