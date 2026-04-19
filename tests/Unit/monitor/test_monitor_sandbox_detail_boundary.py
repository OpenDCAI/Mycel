import inspect

from backend.monitor.infrastructure.web import gateway as monitor_gateway_impl


def test_monitor_gateway_sandbox_detail_uses_narrow_detail_service():
    source = inspect.getsource(monitor_gateway_impl)
    broad_shell = "monitor" + "_service"

    assert "monitor_sandbox_detail_service" in source
    assert f"{broad_shell}.get_monitor_sandbox_detail" not in source
    assert f"{broad_shell}.request_monitor_sandbox_cleanup" not in source
    assert f"{broad_shell}.get_monitor_operation_detail" not in source
