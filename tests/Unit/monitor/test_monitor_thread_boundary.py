import inspect

from backend.monitor.infrastructure.web import gateway as monitor_gateway_impl


def test_monitor_gateway_thread_surfaces_use_narrow_thread_service():
    source = inspect.getsource(monitor_gateway_impl)
    broad_shell = "monitor" + "_service"

    assert "monitor_thread_service" in source
    assert f"{broad_shell}.list_monitor_threads" not in source
    assert f"{broad_shell}.get_monitor_thread_detail" not in source
