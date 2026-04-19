import inspect
from pathlib import Path

from backend.monitor.application.use_cases import threads as monitor_threads_impl
from backend.monitor.infrastructure.web import gateway as monitor_gateway_impl
from backend.web.routers import threads as threads_router_impl


def test_monitor_gateway_thread_surfaces_use_narrow_thread_service():
    source = inspect.getsource(monitor_gateway_impl)
    broad_shell = "monitor" + "_service"

    assert "monitor_threads" in source
    assert f"{broad_shell}.list_monitor_threads" not in source
    assert f"{broad_shell}.get_monitor_thread_detail" not in source
    assert "build_owner_thread_workbench_reader" in source
    assert "build_monitor_thread_base_loader" in source
    assert "build_monitor_trace_reader" in source


def test_monitor_thread_use_case_lives_in_monitor_module():
    parts = Path(monitor_threads_impl.__file__).parts

    assert "backend" in parts
    assert "monitor" in parts


def test_product_threads_router_points_at_monitor_workbench_module():
    source = inspect.getsource(threads_router_impl)

    assert "backend.web.services.owner_thread_workbench_read_service" not in source
    assert "backend.web.services.owner_thread_workbench_service" not in source
    assert "backend.monitor.infrastructure.read_models.thread_workbench_read_service" in source
    assert "backend.monitor.application.use_cases.thread_workbench" in source
