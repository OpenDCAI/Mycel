import inspect

from backend.web.services import (
    monitor_sandbox_detail_service,
    monitor_sandbox_projection_service,
    monitor_sandbox_read_service,
    monitor_thread_read_service,
    monitor_thread_service,
    monitor_thread_trajectory_service,
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


def test_monitor_sandbox_detail_uses_thread_read_port():
    detail_source = inspect.getsource(monitor_sandbox_detail_service)
    read_source = inspect.getsource(monitor_thread_read_service)

    assert "build_thread_repo" not in detail_source
    assert "canonical_owner_threads" not in detail_source
    assert "build_thread_repo" in read_source


def test_monitor_thread_detail_uses_thread_read_port():
    thread_source = inspect.getsource(monitor_thread_service)
    read_source = inspect.getsource(monitor_thread_read_service)

    assert 'getattr(app.state, "thread_repo"' not in thread_source
    assert "_thread_owners" not in thread_source
    assert "load_monitor_thread_base" in thread_source
    assert 'getattr(app.state, "thread_repo"' in read_source


def test_monitor_thread_detail_uses_trajectory_read_port():
    thread_source = inspect.getsource(monitor_thread_service)
    trajectory_source = inspect.getsource(monitor_thread_trajectory_service)

    assert "monitor_trace_service" not in thread_source
    assert "build_monitor_thread_trajectory" not in thread_source
    assert "monitor_thread_trajectory_service" in thread_source
    assert "build_monitor_thread_trajectory" in trajectory_source
