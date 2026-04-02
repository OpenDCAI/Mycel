"""Unit tests for core.runtime.fork context fork."""

from pathlib import Path

import pytest

from core.runtime.fork import create_subagent_context, fork_context
from core.runtime.state import AppState, BootstrapConfig, ToolUseContext


@pytest.fixture
def parent():
    return BootstrapConfig(
        workspace_root=Path("/workspace"),
        original_cwd=Path("/launcher"),
        project_root=Path("/workspace/project"),
        cwd=Path("/workspace/project/src"),
        model_name="claude-opus-4-5",
        api_key="sk-parent",
        block_dangerous_commands=True,
        block_network_commands=True,
        enable_audit_log=False,
        enable_web_tools=True,
        allowed_file_extensions=[".py"],
        extra_allowed_paths=["/shared"],
        max_turns=20,
        model_provider="anthropic",
        base_url="https://api.anthropic.com",
        context_limit=200000,
        total_cost_usd=1.25,
        total_tool_duration_ms=42,
    )


def test_fork_inherits_workspace(parent):
    child = fork_context(parent)
    assert child.workspace_root == parent.workspace_root
    assert child.original_cwd == parent.original_cwd
    assert child.project_root == parent.project_root
    assert child.cwd == parent.cwd


def test_fork_inherits_model(parent):
    child = fork_context(parent)
    assert child.model_name == parent.model_name
    assert child.api_key == parent.api_key


def test_fork_inherits_security_flags(parent):
    child = fork_context(parent)
    assert child.block_dangerous_commands == parent.block_dangerous_commands
    assert child.block_network_commands == parent.block_network_commands
    assert child.enable_audit_log == parent.enable_audit_log
    assert child.enable_web_tools == parent.enable_web_tools


def test_fork_inherits_file_config(parent):
    child = fork_context(parent)
    assert child.allowed_file_extensions == parent.allowed_file_extensions
    assert child.extra_allowed_paths == parent.extra_allowed_paths
    assert child.max_turns == parent.max_turns


def test_fork_inherits_model_settings(parent):
    child = fork_context(parent)
    assert child.model_provider == parent.model_provider
    assert child.base_url == parent.base_url
    assert child.context_limit == parent.context_limit


def test_fork_inherits_session_accumulators(parent):
    child = fork_context(parent)
    assert child.total_cost_usd == parent.total_cost_usd
    assert child.total_tool_duration_ms == parent.total_tool_duration_ms


def test_fork_generates_new_session_id(parent):
    child = fork_context(parent)
    assert child.session_id != parent.session_id


def test_fork_sets_parent_session_id(parent):
    child = fork_context(parent)
    assert child.parent_session_id == parent.session_id


def test_fork_is_independent_object(parent):
    child = fork_context(parent)
    assert child is not parent


def test_multiple_forks_have_unique_session_ids(parent):
    children = [fork_context(parent) for _ in range(10)]
    session_ids = {c.session_id for c in children}
    assert len(session_ids) == 10


@pytest.fixture
def parent_tool_context(parent):
    app_state = AppState(turn_count=1, tool_overrides={"Bash": True})

    def set_app_state_for_tasks(updater):
        app_state.set_state(updater)

    return ToolUseContext(
        bootstrap=parent,
        get_app_state=app_state.get_state,
        set_app_state=app_state.set_state,
        set_app_state_for_tasks=set_app_state_for_tasks,
        refresh_tools=None,
        read_file_state={"/tmp/file.py": {"partial": False}},
        loaded_nested_memory_paths={"/tmp/memory.md"},
        discovered_skill_names={"skill-a"},
        nested_memory_attachment_triggers={"turn-a"},
        messages=["msg-1"],
    )


def test_create_subagent_context_defaults_to_noop_set_app_state(parent_tool_context):
    child = create_subagent_context(parent_tool_context)

    child.set_app_state(lambda prev: prev.model_copy(update={"turn_count": 9}))

    assert parent_tool_context.get_app_state().turn_count == 1


def test_create_subagent_context_keeps_task_state_escape_hatch(parent_tool_context):
    child = create_subagent_context(parent_tool_context)

    child.set_app_state_for_tasks(lambda prev: prev.model_copy(update={"turn_count": 9}))

    assert parent_tool_context.get_app_state().turn_count == 9


def test_create_subagent_context_deep_clones_read_file_state(parent_tool_context):
    parent_tool_context.read_file_state = {
        "/tmp/readme.md": {"partial": False, "meta": {"seen": 1}}
    }

    child = create_subagent_context(parent_tool_context)
    child.read_file_state["/tmp/readme.md"]["partial"] = True
    child.read_file_state["/tmp/readme.md"]["meta"]["seen"] = 9

    assert parent_tool_context.read_file_state["/tmp/readme.md"] == {
        "partial": False,
        "meta": {"seen": 1},
    }
