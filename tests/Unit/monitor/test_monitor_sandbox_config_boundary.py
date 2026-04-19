import inspect

from backend.monitor.application.use_cases import sandbox_configs as sandbox_configs_impl
from backend.monitor.infrastructure.config import app_config_service as app_config_impl
from backend.monitor.infrastructure.providers import sandbox_config_provider_service as sandbox_config_provider_impl
from backend.monitor.infrastructure.web import gateway as monitor_gateway_impl


def test_monitor_gateway_routes_sandbox_config_through_config_service():
    source = inspect.getsource(monitor_gateway_impl)
    broad_shell = "monitor" + "_service"

    assert "sandbox_configs" in source
    assert broad_shell not in source


def test_monitor_sandbox_config_uses_provider_inventory_port():
    config_source = inspect.getsource(sandbox_configs_impl)
    provider_source = inspect.getsource(sandbox_config_provider_impl)
    app_config_source = inspect.getsource(app_config_impl)

    assert "sandbox_service" not in config_source
    assert "backend.web.core" not in config_source
    assert "sandbox_config_provider_service" in config_source
    assert "app_config_service" in config_source
    assert "available_sandbox_types" in provider_source
    assert "backend.web.core" not in app_config_source
    assert "backend.web.services" not in provider_source
