import inspect

from backend.web.services import monitor_sandbox_projection_service, monitor_sandbox_read_service


def test_monitor_sandbox_projection_does_not_construct_runtime_repo():
    projection_source = inspect.getsource(monitor_sandbox_projection_service)
    read_source = inspect.getsource(monitor_sandbox_read_service)

    assert "make_sandbox_monitor_repo" not in projection_source
    assert "make_sandbox_monitor_repo" in read_source
