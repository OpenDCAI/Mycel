import inspect

from backend.monitor.application.use_cases import sandbox_detail as monitor_sandbox_detail_service
from backend.monitor.application.use_cases import sandbox_projection as monitor_sandbox_projection_service
from backend.monitor.application.use_cases import thread_workbench as owner_thread_workbench_service
from backend.monitor.application.use_cases import threads as monitor_thread_service
from backend.monitor.application.use_cases import trace as monitor_trace_service
from backend.monitor.infrastructure.read_models import sandbox_read_service as monitor_sandbox_read_service
from backend.monitor.infrastructure.read_models import thread_read_service as monitor_thread_read_service
from backend.monitor.infrastructure.read_models import thread_workbench_read_service as owner_thread_workbench_read_service
from backend.monitor.infrastructure.read_models import trace_read_service as monitor_trace_read_service


def test_monitor_sandbox_projection_does_not_construct_runtime_repo():
    projection_source = inspect.getsource(monitor_sandbox_projection_service)
    read_source = inspect.getsource(monitor_sandbox_read_service)

    assert "make_sandbox_monitor_repo" not in projection_source
    assert "backend.web.services.resource_common" not in projection_source
    assert "load_live_thread_ids" in projection_source
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
    assert "def get_monitor_thread_detail(app" not in thread_source
    assert "_thread_owners" not in thread_source
    assert "load_thread_base" in thread_source
    assert 'getattr(app.state, "thread_repo"' in read_source


def test_monitor_thread_detail_uses_trajectory_read_port():
    thread_source = inspect.getsource(monitor_thread_service)
    trace_source = inspect.getsource(monitor_trace_service)

    assert "monitor_thread_trajectory_service" not in thread_source
    assert "monitor_trace" in thread_source
    assert "build_monitor_thread_trajectory" in thread_source
    assert "def build_monitor_thread_trajectory(app" not in trace_source
    assert "trace_read_service" in trace_source


def test_monitor_trace_uses_trace_read_source_port():
    trace_source = inspect.getsource(monitor_trace_service)
    read_source = inspect.getsource(monitor_trace_read_service)

    assert "thread_history_service" not in trace_source
    assert "build_storage_container" not in trace_source
    assert "trace_read_service" in trace_source
    assert "get_thread_history_payload" in read_source
    assert "get_thread_history_payload(app=" not in read_source
    assert "build_thread_history_transport" in read_source
    assert "build_storage_container" not in read_source
    assert "build_run_event_read_transport" in read_source


def test_monitor_thread_list_does_not_depend_on_threads_router():
    thread_source = inspect.getsource(monitor_thread_service)

    assert "backend.web.routers.threads" not in thread_source
    assert "thread_workbench" in thread_source
    assert "def list_monitor_threads(app" not in thread_source


def test_owner_thread_workbench_uses_app_state_read_source():
    workbench_source = inspect.getsource(owner_thread_workbench_service)
    read_source = inspect.getsource(owner_thread_workbench_read_service)

    assert "app.state" not in workbench_source
    assert "def build_owner_thread_workbench(app" not in workbench_source
    assert "backend.web.services.thread_visibility" not in workbench_source
    assert "backend.web.utils.serializers" not in workbench_source
    assert "thread_workbench_read_service" in workbench_source
    assert "app.state" in read_source
    assert "canonical_owner_threads" in read_source
    assert "avatar_url" in read_source
