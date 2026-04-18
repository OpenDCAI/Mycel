import inspect

from backend.web.services import (
    monitor_gateway,
    monitor_sandbox_config_provider_service,
    monitor_sandbox_config_service,
)


def test_monitor_gateway_routes_sandbox_config_through_config_service():
    source = inspect.getsource(monitor_gateway)
    broad_shell = "monitor" + "_service"

    assert "monitor_sandbox_config_service" in source
    assert broad_shell not in source


def test_monitor_sandbox_config_uses_provider_inventory_port():
    config_source = inspect.getsource(monitor_sandbox_config_service)
    provider_source = inspect.getsource(monitor_sandbox_config_provider_service)

    assert "sandbox_service" not in config_source
    assert "monitor_sandbox_config_provider_service" in config_source
    assert "available_sandbox_types" in provider_source
