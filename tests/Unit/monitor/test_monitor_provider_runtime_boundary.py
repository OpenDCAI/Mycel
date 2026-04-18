import inspect

from backend.web.services import monitor_gateway


def test_monitor_gateway_provider_runtime_uses_narrow_service():
    source = inspect.getsource(monitor_gateway)
    broad_shell = "monitor" + "_service"

    assert "monitor_provider_runtime_service" in source
    assert f"{broad_shell}.list_monitor_provider_orphan_runtimes" not in source
    assert f"{broad_shell}.get_monitor_provider_detail" not in source
    assert f"{broad_shell}.get_monitor_runtime_detail" not in source
    assert f"{broad_shell}.request_monitor_provider_orphan_runtime_cleanup" not in source
