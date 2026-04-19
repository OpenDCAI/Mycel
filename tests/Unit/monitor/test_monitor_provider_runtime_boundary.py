import inspect

from backend.monitor.infrastructure.web import gateway as monitor_gateway_impl
from backend.web.services import monitor_provider_runtime_inventory_service, monitor_provider_runtime_service


def test_monitor_gateway_provider_runtime_uses_narrow_service():
    source = inspect.getsource(monitor_gateway_impl)
    broad_shell = "monitor" + "_service"

    assert "monitor_provider_runtime_service" in source
    assert f"{broad_shell}.list_monitor_provider_orphan_runtimes" not in source
    assert f"{broad_shell}.get_monitor_provider_detail" not in source
    assert f"{broad_shell}.get_monitor_runtime_detail" not in source
    assert f"{broad_shell}.request_monitor_provider_orphan_runtime_cleanup" not in source


def test_monitor_provider_runtime_uses_inventory_read_port():
    source = inspect.getsource(monitor_provider_runtime_service)
    inventory_source = inspect.getsource(monitor_provider_runtime_inventory_service)

    assert "sandbox_service" not in source
    assert "init_providers_and_managers" not in source
    assert "load_provider_orphan_runtime_rows" in source
    assert "init_providers_and_managers" in inventory_source
    assert "load_provider_orphan_runtimes" in inventory_source
