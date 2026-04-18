import inspect

from backend.web.services import monitor_gateway, resource_cache


def test_resource_cache_uses_narrow_sandbox_projection_not_monitor_service():
    source = inspect.getsource(resource_cache)

    assert "monitor_service" not in source
    assert "monitor_sandbox_projection_service" in source


def test_monitor_gateway_sandbox_list_uses_narrow_projection_service():
    source = inspect.getsource(monitor_gateway.list_sandboxes)

    assert "monitor_service.list_monitor_sandboxes" not in source
    assert "monitor_sandbox_projection_service" in inspect.getsource(monitor_gateway)
