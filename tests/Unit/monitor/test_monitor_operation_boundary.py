import inspect
from pathlib import Path

from backend.web.services import (
    monitor_operation_repo_service,
    monitor_operation_service,
    monitor_runtime_mutation_service,
)


def test_monitor_operation_service_delegates_runtime_mutation_to_executor():
    source = inspect.getsource(monitor_operation_service)

    assert "sandbox_service" not in source
    assert "destroy_sandbox_runtime" not in source
    assert "mutate_sandbox_runtime" not in source


def test_monitor_operation_service_uses_runtime_mutation_port():
    source = inspect.getsource(monitor_operation_service)
    port_source = inspect.getsource(monitor_runtime_mutation_service)
    services_dir = Path(monitor_operation_service.__file__).parent

    assert "_sandbox_destroy_result" not in source
    assert "_provider_runtime_destroy_result" not in source
    assert "monitor_runtime_operation_service" not in source
    assert not (services_dir / "monitor_runtime_operation_service.py").exists()
    assert "RuntimeMutationResult" in port_source
    assert "destroy_result" in port_source


def test_monitor_operation_service_uses_operation_repo_boundary():
    source = inspect.getsource(monitor_operation_service)
    repo_source = inspect.getsource(monitor_operation_repo_service)

    assert "_OPERATIONS" not in source
    assert "_TARGET_INDEX" not in source
    assert "_LOCK" not in source
    assert "InMemoryMonitorOperationRepo" in repo_source
