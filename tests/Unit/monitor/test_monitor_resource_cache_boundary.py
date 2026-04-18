import inspect

from backend.web.services import monitor_gateway, resource_cache


def test_resource_cache_uses_narrow_sandbox_projection_not_broad_monitor_shell():
    source = inspect.getsource(resource_cache)
    broad_shell = "monitor" + "_service"

    assert broad_shell not in source
    assert "monitor_sandbox_projection_service" in source


def test_monitor_gateway_sandbox_list_uses_narrow_projection_service():
    source = inspect.getsource(monitor_gateway.list_sandboxes)
    broad_shell = "monitor" + "_service"

    assert f"{broad_shell}.list_monitor_sandboxes" not in source
    assert "monitor_sandbox_projection_service" in inspect.getsource(monitor_gateway)
