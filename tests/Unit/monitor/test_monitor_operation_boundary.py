import inspect

from backend.monitor.application.use_cases import operations as monitor_operations_impl
from backend.monitor.infrastructure.persistence import operation_repo as monitor_operation_repo_impl
from backend.monitor.infrastructure.web import gateway as monitor_gateway_impl
from backend.monitor.mutations import sandbox_mutations as monitor_runtime_mutation_impl


def test_monitor_operation_service_delegates_runtime_mutation_to_executor():
    source = inspect.getsource(monitor_operations_impl)

    assert "sandbox_service" not in source
    assert "destroy_sandbox_runtime" not in source
    assert "mutate_sandbox_runtime" not in source


def test_monitor_operation_service_uses_runtime_mutation_port():
    source = inspect.getsource(monitor_operations_impl)
    gateway_source = inspect.getsource(monitor_gateway_impl)
    port_source = inspect.getsource(monitor_runtime_mutation_impl)

    assert "_sandbox_destroy_result" not in source
    assert "_provider_runtime_destroy_result" not in source
    assert "monitor_runtime_operation_service" not in source
    assert "execute_sandbox_cleanup" not in source
    assert "execute_provider_orphan_runtime_cleanup" not in source
    assert "sandbox_mutations" not in source
    assert "SandboxCleanupCommand" not in source
    assert "ProviderOrphanRuntimeCleanupCommand" not in source
    assert "build_runtime_mutation_executor" not in gateway_source
    assert "sandbox_mutations" in gateway_source
    assert "RuntimeMutationResult" in port_source
    assert "destroy_result" in port_source
    assert "def cleanup_sandbox(" in port_source
    assert "def cleanup_provider_orphan_runtime(" in port_source
    assert "def build_runtime_mutation_executor(" not in port_source


def test_monitor_operation_service_uses_operation_repo_boundary():
    source = inspect.getsource(monitor_operations_impl)
    repo_source = inspect.getsource(monitor_operation_repo_impl)

    assert "_OPERATIONS" not in source
    assert "_TARGET_INDEX" not in source
    assert "_LOCK" not in source
    assert "MonitorOperationRepo" in repo_source
    assert "InMemoryMonitorOperationRepo" in repo_source
    assert "build_storage_container" in repo_source
    assert "def default_monitor_operation_repo() -> MonitorOperationRepo:" in repo_source


def test_default_monitor_operation_repo_uses_storage_container_boundary(monkeypatch):
    repo = object()

    class _Container:
        def monitor_operation_repo(self):
            return repo

    monkeypatch.setattr(monitor_operation_repo_impl, "_default_monitor_operation_repo", None)
    monkeypatch.setattr(monitor_operation_repo_impl, "build_storage_container", lambda: _Container())

    assert monitor_operation_repo_impl.default_monitor_operation_repo() is repo


def test_default_monitor_operation_repo_fails_loudly_when_storage_repo_is_unavailable(monkeypatch):
    monkeypatch.setattr(monitor_operation_repo_impl, "_default_monitor_operation_repo", None)
    monkeypatch.setattr(
        monitor_operation_repo_impl,
        "build_storage_container",
        lambda: (_ for _ in ()).throw(RuntimeError("monitor operation repo unavailable")),
    )

    try:
        monitor_operation_repo_impl.default_monitor_operation_repo()
    except RuntimeError as exc:
        assert str(exc) == "monitor operation repo unavailable"
    else:
        raise AssertionError("expected RuntimeError")
