import inspect

from backend.web.services import monitor_gateway


def test_monitor_gateway_evaluation_surfaces_use_narrow_evaluation_service():
    source = inspect.getsource(monitor_gateway)

    assert "monitor_evaluation_service" in source
    assert "monitor_service.get_monitor_evaluation_workbench" not in source
    assert "monitor_service.get_monitor_evaluation_batches" not in source
    assert "monitor_service.create_monitor_evaluation_batch" not in source
    assert "monitor_service.get_monitor_evaluation_scenarios" not in source
    assert "monitor_service.start_monitor_evaluation_batch" not in source
    assert "monitor_service.get_monitor_evaluation_batch_detail" not in source
    assert "monitor_service.get_monitor_evaluation_run_detail" not in source
