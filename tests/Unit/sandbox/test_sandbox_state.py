"""Tests for sandbox state mapping logic."""

from storage.models import (
    map_sandbox_state_to_display_status,
)


def test_map_running_state():
    """Test mapping of running state (detached + running)."""
    assert map_sandbox_state_to_display_status("detached", "running") == "running"


def test_map_pausing_state():
    """Test mapping of pausing in progress (detached + paused)."""
    assert map_sandbox_state_to_display_status("detached", "paused") == "paused"


def test_map_paused_state():
    """Test mapping of paused state (paused + paused)."""
    assert map_sandbox_state_to_display_status("paused", "paused") == "paused"


def test_map_stopped_state():
    """Test mapping of stopped state (None)."""
    assert map_sandbox_state_to_display_status(None, None) == "stopped"
    assert map_sandbox_state_to_display_status(None, "running") == "stopped"


def test_map_destroying_state():
    """Test mapping of destroying state (any + destroyed)."""
    assert map_sandbox_state_to_display_status("detached", "destroyed") == "destroying"
    assert map_sandbox_state_to_display_status("paused", "destroyed") == "destroying"


def test_case_insensitive():
    """Test that mapping is case-insensitive."""
    assert map_sandbox_state_to_display_status("DETACHED", "RUNNING") == "running"
    assert map_sandbox_state_to_display_status("Paused", "Paused") == "paused"


def test_whitespace_handling():
    """Test that mapping handles whitespace."""
    assert map_sandbox_state_to_display_status(" detached ", " running ") == "running"


def test_unknown_state():
    """Test that unknown states are treated as stopped."""
    assert map_sandbox_state_to_display_status("unknown", "running") == "stopped"
