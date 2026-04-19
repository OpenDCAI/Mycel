import inspect

from backend import auth_dependencies
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
