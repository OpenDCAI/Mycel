import inspect

from backend import auth_runtime_bootstrap, avatar_files
from backend import auth_service as neutral_auth_service
from backend.web.routers import users as users_router
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
