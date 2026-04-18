import inspect

from backend.web.services import (
    monitor_evaluation_execution_service,
    monitor_evaluation_read_service,
    monitor_evaluation_service,
    monitor_gateway,
)


def test_monitor_gateway_evaluation_surfaces_use_narrow_evaluation_service():
    source = inspect.getsource(monitor_gateway)
    broad_shell = "monitor" + "_service"

    assert "monitor_evaluation_service" in source
    assert f"{broad_shell}.get_monitor_evaluation_workbench" not in source
    assert f"{broad_shell}.get_monitor_evaluation_batches" not in source
    assert f"{broad_shell}.create_monitor_evaluation_batch" not in source
    assert f"{broad_shell}.get_monitor_evaluation_scenarios" not in source
    assert f"{broad_shell}.start_monitor_evaluation_batch" not in source
    assert f"{broad_shell}.get_monitor_evaluation_batch_detail" not in source
    assert f"{broad_shell}.get_monitor_evaluation_run_detail" not in source


def test_monitor_evaluation_service_uses_execution_port_for_runtime_work():
    service_source = inspect.getsource(monitor_evaluation_service)
    execution_source = inspect.getsource(monitor_evaluation_execution_service)

    assert "monitor_evaluation_execution_service" in service_source
    assert "load_scenarios_from_dir" not in service_source
    assert "EVAL_SCENARIO_DIR" not in service_source
    assert "EvalClient" not in service_source
    assert "EvalRunner" not in service_source
    assert "EvaluationBatchExecutor" not in service_source

    assert "load_scenarios_from_dir" in execution_source
    assert "EvalClient" in execution_source
    assert "EvalRunner" in execution_source
    assert "EvaluationBatchExecutor" in execution_source


def test_monitor_evaluation_service_uses_read_source_for_store_and_batch_repo():
    service_source = inspect.getsource(monitor_evaluation_service)
    read_source = inspect.getsource(monitor_evaluation_read_service)

    assert "monitor_evaluation_read_service" in service_source
    assert "TrajectoryStore" not in service_source
    assert "build_evaluation_batch_repo" not in service_source

    assert "TrajectoryStore" in read_source
    assert "build_evaluation_batch_repo" in read_source
