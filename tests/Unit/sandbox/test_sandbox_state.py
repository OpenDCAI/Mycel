from storage.models import (
    map_sandbox_state_to_display_status,
)


def test_map_running_state():
    assert map_sandbox_state_to_display_status("detached", "running") == "running"


def test_map_pausing_state():
    assert map_sandbox_state_to_display_status("detached", "paused") == "paused"


def test_map_paused_state():
    assert map_sandbox_state_to_display_status("paused", "paused") == "paused"


def test_map_stopped_state():
    assert map_sandbox_state_to_display_status(None, None) == "stopped"
    assert map_sandbox_state_to_display_status(None, "running") == "stopped"


def test_map_destroying_state():
    assert map_sandbox_state_to_display_status("detached", "destroyed") == "destroying"
    assert map_sandbox_state_to_display_status("paused", "destroyed") == "destroying"


def test_case_insensitive():
    assert map_sandbox_state_to_display_status("DETACHED", "RUNNING") == "running"
    assert map_sandbox_state_to_display_status("Paused", "Paused") == "paused"


def test_whitespace_handling():
    assert map_sandbox_state_to_display_status(" detached ", " running ") == "running"


def test_unknown_state():
    assert map_sandbox_state_to_display_status("unknown", "running") == "stopped"
