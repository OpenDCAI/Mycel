import inspect

from backend.monitor.application.use_cases import threads as monitor_threads_impl
from backend.monitor.infrastructure.web import gateway as monitor_gateway_impl


def test_monitor_gateway_thread_surfaces_use_narrow_thread_service():
    source = inspect.getsource(monitor_gateway_impl)
    broad_shell = "monitor" + "_service"

    assert "monitor_threads" in source
    assert f"{broad_shell}.list_monitor_threads" not in source
    assert f"{broad_shell}.get_monitor_thread_detail" not in source


def test_monitor_thread_use_case_lives_in_monitor_module():
    assert "/backend/monitor/" in monitor_threads_impl.__file__
