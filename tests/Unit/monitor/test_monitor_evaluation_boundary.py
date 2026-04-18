import inspect

from backend.web.services import monitor_gateway


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
