from backend import auth_dependencies, auth_user_resolution, request_app
from backend.web.core import dependencies as web_dependencies


def test_web_dependency_getter_is_compat_alias():
    assert web_dependencies._get_auth_service is auth_dependencies._get_auth_service


def test_web_current_user_resolution_is_compat_alias():
    assert web_dependencies.get_current_user is auth_user_resolution.get_current_user
    assert web_dependencies.get_current_user_id is auth_user_resolution.get_current_user_id


def test_web_get_app_is_compat_alias():
    assert web_dependencies.get_app is request_app.get_app
