import inspect

from backend.monitor.application.use_cases import operations as monitor_operations_impl
from backend.monitor.infrastructure.persistence import operation_repo as monitor_operation_repo_impl
from backend.monitor.infrastructure.runtime import runtime_mutation_service as monitor_runtime_mutation_impl


def test_monitor_operation_service_delegates_runtime_mutation_to_executor():
    source = inspect.getsource(monitor_operations_impl)

    assert "sandbox_service" not in source
    assert "destroy_sandbox_runtime" not in source
    assert "mutate_sandbox_runtime" not in source


def test_monitor_operation_service_uses_runtime_mutation_port():
    source = inspect.getsource(monitor_operations_impl)
    port_source = inspect.getsource(monitor_runtime_mutation_impl)

    assert "_sandbox_destroy_result" not in source
    assert "_provider_runtime_destroy_result" not in source
    assert "monitor_runtime_operation_service" not in source
    assert "RuntimeMutationResult" in port_source
    assert "destroy_result" in port_source


def test_monitor_operation_service_uses_operation_repo_boundary():
    source = inspect.getsource(monitor_operations_impl)
    repo_source = inspect.getsource(monitor_operation_repo_impl)

    assert "_OPERATIONS" not in source
    assert "_TARGET_INDEX" not in source
    assert "_LOCK" not in source
    assert "MonitorOperationRepo(Protocol)" in repo_source
    assert "InMemoryMonitorOperationRepo" in repo_source
    assert "def default_monitor_operation_repo() -> MonitorOperationRepo:" in repo_source
