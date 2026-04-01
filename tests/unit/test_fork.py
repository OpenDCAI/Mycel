"""Unit tests for core.runtime.fork context fork."""

from pathlib import Path

import pytest

from core.runtime.fork import fork_context
from core.runtime.state import BootstrapConfig


@pytest.fixture
def parent():
    return BootstrapConfig(
        workspace_root=Path("/workspace"),
        model_name="claude-opus-4-5",
        api_key="sk-parent",
        block_dangerous_commands=True,
        block_network_commands=True,
        enable_audit_log=False,
        enable_web_tools=True,
        allowed_file_extensions=[".py"],
        max_turns=20,
        model_provider="anthropic",
        base_url="https://api.anthropic.com",
        context_limit=200000,
    )


def test_fork_inherits_workspace(parent):
    child = fork_context(parent)
    assert child.workspace_root == parent.workspace_root


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
    assert child.max_turns == parent.max_turns


def test_fork_inherits_model_settings(parent):
    child = fork_context(parent)
    assert child.model_provider == parent.model_provider
    assert child.base_url == parent.base_url
    assert child.context_limit == parent.context_limit


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
