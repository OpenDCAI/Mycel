import inspect

from backend.web.services import monitor_gateway


def test_monitor_gateway_routes_sandbox_config_through_config_service():
    source = inspect.getsource(monitor_gateway)
    broad_shell = "monitor" + "_service"

    assert "monitor_sandbox_config_service" in source
    assert broad_shell not in source
