"""Unit tests for core.runtime.state three-layer state models."""

from pathlib import Path

import pytest

from core.runtime.state import AppState, BootstrapConfig, ToolUseContext


class TestBootstrapConfig:
    def test_minimal_creation(self):
        bc = BootstrapConfig(workspace_root=Path("/tmp"), model_name="claude-3-5-sonnet-20241022")
        assert bc.workspace_root == Path("/tmp")
        assert bc.model_name == "claude-3-5-sonnet-20241022"
        assert bc.api_key is None

    def test_security_fail_closed_defaults(self):
        bc = BootstrapConfig(workspace_root=Path("/tmp"), model_name="test")
        assert bc.block_dangerous_commands is True
        assert bc.block_network_commands is False
        assert bc.enable_audit_log is True

    def test_all_fields(self):
        bc = BootstrapConfig(
            workspace_root=Path("/workspace"),
            model_name="claude-opus-4-5",
            api_key="sk-test",
            block_dangerous_commands=False,
            enable_web_tools=True,
            allowed_file_extensions=[".py", ".ts"],
            max_turns=50,
        )
        assert bc.api_key == "sk-test"
        assert bc.enable_web_tools is True
        assert bc.allowed_file_extensions == [".py", ".ts"]
        assert bc.max_turns == 50

    def test_session_id_generated(self):
        bc1 = BootstrapConfig(workspace_root=Path("/tmp"), model_name="test")
        bc2 = BootstrapConfig(workspace_root=Path("/tmp"), model_name="test")
        assert bc1.session_id != bc2.session_id
        assert len(bc1.session_id) == 32  # uuid4().hex


class TestAppState:
    def test_default_values(self):
        s = AppState()
        assert s.messages == []
        assert s.turn_count == 0
        assert s.total_cost == 0.0
        assert s.compact_boundary_index == 0

    def test_get_state_returns_self(self):
        s = AppState()
        assert s.get_state() is s

    def test_set_state_applies_updater(self):
        s = AppState()
        s.set_state(lambda prev: AppState(turn_count=prev.turn_count + 1))
        assert s.turn_count == 1

    def test_set_state_multiple_fields(self):
        s = AppState()
        s.set_state(lambda prev: AppState(turn_count=5, total_cost=1.23))
        assert s.turn_count == 5
        assert s.total_cost == 1.23

    def test_tool_overrides(self):
        s = AppState(tool_overrides={"Bash": False})
        assert s.tool_overrides["Bash"] is False


class TestToolUseContext:
    def test_creation(self):
        bc = BootstrapConfig(workspace_root=Path("/tmp"), model_name="test")
        app_state = AppState()
        ctx = ToolUseContext(
            bootstrap=bc,
            get_app_state=lambda: app_state,
            set_app_state=lambda _: None,
        )
        assert ctx.bootstrap is bc
        assert ctx.get_app_state() is app_state

    def test_turn_id_generated(self):
        bc = BootstrapConfig(workspace_root=Path("/tmp"), model_name="test")
        ctx1 = ToolUseContext(bootstrap=bc, get_app_state=lambda: None, set_app_state=lambda _: None)
        ctx2 = ToolUseContext(bootstrap=bc, get_app_state=lambda: None, set_app_state=lambda _: None)
        assert ctx1.turn_id != ctx2.turn_id
        assert len(ctx1.turn_id) == 8

    def test_subagent_noop_set_state(self):
        """Sub-agents should use a NO-OP set_app_state to prevent write-through."""
        bc = BootstrapConfig(workspace_root=Path("/tmp"), model_name="test")
        app_state = AppState(turn_count=5)
        calls = []
        noop = lambda _: calls.append("called")
        ctx = ToolUseContext(bootstrap=bc, get_app_state=lambda: app_state, set_app_state=noop)
        ctx.set_app_state(AppState(turn_count=99))
        # noop was called but original state is unchanged (illustrates isolation pattern)
        assert len(calls) == 1
        assert app_state.turn_count == 5
