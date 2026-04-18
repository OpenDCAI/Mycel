import inspect

from backend.web.services import monitor_operation_service, monitor_runtime_operation_service


def test_monitor_operation_service_delegates_runtime_mutation_to_executor():
    source = inspect.getsource(monitor_operation_service)

    assert "sandbox_service" not in source
    assert "destroy_sandbox_runtime" not in source
    assert "mutate_sandbox_runtime" not in source


def test_monitor_runtime_executor_owns_destroy_result_shaping():
    source = inspect.getsource(monitor_operation_service)
    executor_source = inspect.getsource(monitor_runtime_operation_service)

    assert "_sandbox_destroy_result" not in source
    assert "_provider_runtime_destroy_result" not in source
    assert "RuntimeMutationResult" in executor_source
    assert "destroy_result" in executor_source
