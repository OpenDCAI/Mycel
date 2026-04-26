from pathlib import Path

from backend.monitor.application.use_cases import threads as monitor_threads_impl


def test_monitor_thread_use_case_lives_in_monitor_module():
    parts = Path(monitor_threads_impl.__file__).parts

    assert "backend" in parts
    assert "monitor" in parts
