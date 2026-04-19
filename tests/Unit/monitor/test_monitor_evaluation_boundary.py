import inspect

from backend.monitor.application.use_cases import evaluation as monitor_evaluation_service
from backend.monitor.infrastructure.evaluation import (
    evaluation_execution_service as monitor_evaluation_execution_service,
)
from backend.monitor.infrastructure.evaluation import (
    evaluation_read_service as monitor_evaluation_read_service,
)
from backend.monitor.infrastructure.evaluation import (
    evaluation_storage_service as monitor_evaluation_storage_service,
)
from backend.monitor.infrastructure.web import gateway as monitor_gateway_impl


def test_monitor_gateway_evaluation_surfaces_use_narrow_evaluation_service():
    source = inspect.getsource(monitor_gateway_impl)

    assert "monitor_evaluation_service" not in source
    assert "from backend.monitor.application.use_cases import evaluation as monitor_evaluation" in source


def test_monitor_evaluation_service_uses_execution_port_for_runtime_work():
    service_source = inspect.getsource(monitor_evaluation_service)
    execution_source = inspect.getsource(monitor_evaluation_execution_service)

    assert "evaluation_execution_service" in service_source
    assert "run_monitor_evaluation_batch" not in service_source
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
    storage_source = inspect.getsource(monitor_evaluation_storage_service)

    assert "evaluation_read_service" in service_source
    assert "TrajectoryStore" not in service_source
    assert "build_evaluation_batch_repo" not in service_source

    assert "evaluation_storage_service" in read_source
    assert "TrajectoryStore" not in read_source
    assert "build_evaluation_batch_repo" not in read_source
    assert "TrajectoryStore" in storage_source
    assert "build_evaluation_batch_repo" in storage_source


def test_monitor_evaluation_execution_uses_storage_port_for_runner_store():
    execution_source = inspect.getsource(monitor_evaluation_execution_service)
    storage_source = inspect.getsource(monitor_evaluation_storage_service)

    assert "evaluation_storage_service" in execution_source
    assert "TrajectoryStore" not in execution_source
    assert "make_trajectory_store" in storage_source
