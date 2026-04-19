import inspect

from backend import auth_runtime_bootstrap
from backend import auth_service as neutral_auth_service
from backend.web.services.auth_service import AuthService


def test_auth_runtime_bootstrap_depends_on_neutral_auth_service():
    source = inspect.getsource(auth_runtime_bootstrap)

    assert "backend.web.services.auth_service" not in source
    assert "backend.auth_service" in source


def test_web_auth_service_is_compat_shell():
    assert AuthService is neutral_auth_service.AuthService
