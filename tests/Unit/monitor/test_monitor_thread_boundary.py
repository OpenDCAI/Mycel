import inspect

from backend.web.services import monitor_gateway


def test_monitor_gateway_thread_surfaces_use_narrow_thread_service():
    source = inspect.getsource(monitor_gateway)

    assert "monitor_thread_service" in source
    assert "monitor_service.list_monitor_threads" not in source
    assert "monitor_service.get_monitor_thread_detail" not in source
