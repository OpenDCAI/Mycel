import inspect

from backend.monitor.application.use_cases import provider_runtimes as provider_runtimes_impl
from backend.monitor.infrastructure.providers import provider_runtime_inventory_service as provider_runtime_inventory_impl
from backend.monitor.infrastructure.web import gateway as monitor_gateway_impl


def test_monitor_gateway_provider_runtime_uses_narrow_service():
    source = inspect.getsource(monitor_gateway_impl)
    broad_shell = "monitor" + "_service"

    assert "monitor_provider_runtimes" in source
    assert f"{broad_shell}.list_monitor_provider_orphan_runtimes" not in source
    assert f"{broad_shell}.get_monitor_provider_detail" not in source
    assert f"{broad_shell}.get_monitor_runtime_detail" not in source
    assert f"{broad_shell}.request_monitor_provider_orphan_runtime_cleanup" not in source


def test_monitor_provider_runtime_uses_inventory_read_port():
    source = inspect.getsource(provider_runtimes_impl)
    inventory_source = inspect.getsource(provider_runtime_inventory_impl)

    assert "sandbox_service" not in source
    assert "init_providers_and_managers" not in source
    assert "load_provider_orphan_runtime_rows" in source
    assert "init_providers_and_managers" not in inventory_source
    assert "load_provider_orphan_runtimes(" not in inventory_source
    assert "list_provider_orphan_runtimes(" in inventory_source
