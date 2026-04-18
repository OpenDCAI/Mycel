import inspect

from backend.web.services import monitor_gateway


def test_monitor_gateway_provider_runtime_uses_narrow_service():
    source = inspect.getsource(monitor_gateway)

    assert "monitor_provider_runtime_service" in source
    assert "monitor_service.list_monitor_provider_orphan_runtimes" not in source
    assert "monitor_service.get_monitor_provider_detail" not in source
    assert "monitor_service.get_monitor_runtime_detail" not in source
    assert "monitor_service.request_monitor_provider_orphan_runtime_cleanup" not in source
