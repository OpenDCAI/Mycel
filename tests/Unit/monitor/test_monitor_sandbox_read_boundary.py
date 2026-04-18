import inspect

from backend.web.services import (
    monitor_sandbox_detail_service,
    monitor_sandbox_projection_service,
    monitor_sandbox_read_service,
    monitor_thread_service,
)


def test_monitor_sandbox_projection_does_not_construct_runtime_repo():
    projection_source = inspect.getsource(monitor_sandbox_projection_service)
    read_source = inspect.getsource(monitor_sandbox_read_service)

    assert "make_sandbox_monitor_repo" not in projection_source
    assert "make_sandbox_monitor_repo" in read_source


def test_monitor_sandbox_detail_does_not_construct_runtime_repo():
    detail_source = inspect.getsource(monitor_sandbox_detail_service)
    read_source = inspect.getsource(monitor_sandbox_read_service)

    assert "make_sandbox_monitor_repo" not in detail_source
    assert "make_sandbox_monitor_repo" in read_source


def test_monitor_thread_detail_does_not_construct_runtime_repo():
    thread_source = inspect.getsource(monitor_thread_service)
    read_source = inspect.getsource(monitor_sandbox_read_service)

    assert "make_sandbox_monitor_repo" not in thread_source
    assert "make_sandbox_monitor_repo" in read_source
