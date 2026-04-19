import inspect

from backend import auth_dependencies, auth_user_resolution, request_app
from backend.web.core import dependencies as web_dependencies
from backend.web.routers import auth as auth_router


def test_web_dependencies_import_auth_service_getter_from_neutral_owner():
    source = inspect.getsource(web_dependencies)

    assert "from backend.auth_dependencies import _get_auth_service" in source
    assert "def _get_auth_service(" not in source


def test_auth_router_uses_neutral_auth_dependency_owner():
    source = inspect.getsource(auth_router)

    assert "from backend.auth_dependencies import _get_auth_service" in source
    assert "from backend.web.core.dependencies import _get_auth_service" not in source


def test_web_dependency_getter_is_compat_alias():
    assert web_dependencies._get_auth_service is auth_dependencies._get_auth_service


def test_web_dependencies_import_current_user_resolution_from_neutral_owner():
    source = inspect.getsource(web_dependencies)

    assert "from backend.auth_user_resolution import get_current_user" in source
    assert "from backend.auth_user_resolution import get_current_user_id" in source
    assert "async def get_current_user(" not in source
    assert "async def get_current_user_id(" not in source


def test_web_current_user_resolution_is_compat_alias():
    assert web_dependencies.get_current_user is auth_user_resolution.get_current_user
    assert web_dependencies.get_current_user_id is auth_user_resolution.get_current_user_id


def test_web_dependencies_import_get_app_from_neutral_owner():
    source = inspect.getsource(web_dependencies)

    assert "from backend.request_app import get_app" in source
    assert "async def get_app(" not in source


def test_web_get_app_is_compat_alias():
    assert web_dependencies.get_app is request_app.get_app
