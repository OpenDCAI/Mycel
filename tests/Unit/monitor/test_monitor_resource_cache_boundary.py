import inspect

from backend.monitor.application.use_cases import provider_runtimes as provider_runtimes_impl
from backend.monitor.application.use_cases import resources as resources_impl
from backend.monitor.infrastructure.io import resource_io_service as resource_io_impl
from backend.monitor.infrastructure.read_models import resource_read_service as resource_read_impl
from backend.monitor.infrastructure.read_models import resource_runtime_service as resource_runtime_impl
from backend.monitor.infrastructure.web import gateway as monitor_gateway_impl
from backend.web.services import (
    resource_cache,
    resource_projection_service,
)


def test_resource_cache_does_not_import_monitor_sandbox_projection():
    source = inspect.getsource(resource_cache)
    broad_shell = "monitor" + "_service"

    assert broad_shell not in source
    assert "monitor_sandbox_projection_service" not in source


def test_resource_cache_refresh_loop_uses_resource_io_port():
    source = inspect.getsource(resource_cache)

    assert "resource_io_service" in source
    assert "resource_service" not in source


def test_monitor_resource_service_owns_resource_triage_composition():
    source = inspect.getsource(resources_impl)

    assert "sandbox_projection" in source


def test_monitor_resource_service_uses_resource_io_port():
    source = inspect.getsource(resources_impl)
    io_source = inspect.getsource(resource_io_impl)

    assert "resource_io_service" in source
    assert "resource_service" not in source
    assert "refresh_resource_snapshots" in io_source
    assert "browse_sandbox" in io_source
    assert "read_sandbox" in io_source


def test_resource_projection_does_not_construct_monitor_runtime_repo():
    source = inspect.getsource(resource_projection_service)
    runtime_source = inspect.getsource(resource_runtime_impl)
    read_source = inspect.getsource(resource_read_impl)

    assert "make_sandbox_monitor_repo" not in source
    assert "list_resource_snapshots_by_sandbox" not in source
    assert "make_sandbox_monitor_repo" not in runtime_source
    assert "list_resource_snapshots_by_sandbox" not in runtime_source
    assert "make_sandbox_monitor_repo" in read_source
    assert "list_resource_snapshots_by_sandbox" in read_source


def test_resource_projection_uses_product_resource_boundary():
    source = inspect.getsource(resource_projection_service)

    assert "sandbox_service" not in source
    assert "resource_service" not in source


def test_monitor_gateway_sandbox_list_uses_narrow_projection_service():
    source = inspect.getsource(monitor_gateway_impl.list_sandboxes)

    assert "monitor_sandbox_projection_service" not in source
    assert "sandbox_projection" in inspect.getsource(monitor_gateway_impl)


def test_monitor_gateway_resource_and_provider_runtime_use_cases_live_in_monitor_module():
    gateway_source = inspect.getsource(monitor_gateway_impl)

    assert "resources as monitor_resources" in gateway_source
    assert "provider_runtimes as monitor_provider_runtimes" in gateway_source


def test_monitor_provider_runtime_module_uses_inventory_port():
    source = inspect.getsource(provider_runtimes_impl)

    assert "monitor_provider_runtime_inventory_service" not in source
    assert "provider_runtime_inventory_service" in source
