import inspect

from backend.web.services import (
    monitor_gateway,
    monitor_resource_io_service,
    monitor_resource_read_service,
    monitor_resource_runtime_service,
    monitor_resource_service,
    resource_cache,
    resource_projection_service,
)


def test_resource_cache_does_not_import_monitor_sandbox_projection():
    source = inspect.getsource(resource_cache)
    broad_shell = "monitor" + "_service"

    assert broad_shell not in source
    assert "monitor_sandbox_projection_service" not in source


def test_monitor_resource_service_owns_resource_triage_composition():
    source = inspect.getsource(monitor_resource_service)

    assert "monitor_sandbox_projection_service" in source


def test_monitor_resource_service_uses_resource_io_port():
    source = inspect.getsource(monitor_resource_service)
    io_source = inspect.getsource(monitor_resource_io_service)

    assert "monitor_resource_io_service" in source
    assert "resource_service" not in source
    assert "refresh_resource_snapshots" in io_source
    assert "browse_sandbox" in io_source
    assert "read_sandbox" in io_source


def test_resource_projection_does_not_construct_monitor_runtime_repo():
    source = inspect.getsource(resource_projection_service)
    runtime_source = inspect.getsource(monitor_resource_runtime_service)
    read_source = inspect.getsource(monitor_resource_read_service)

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
    source = inspect.getsource(monitor_gateway.list_sandboxes)
    broad_shell = "monitor" + "_service"

    assert f"{broad_shell}.list_monitor_sandboxes" not in source
    assert "monitor_sandbox_projection_service" in inspect.getsource(monitor_gateway)
