"""Focused runtime support tests for cleanup, fork, and state helpers."""

import asyncio
import signal
from pathlib import Path
from typing import Any, get_type_hints

import pytest

from core.runtime.abort import AbortController
from core.runtime.cleanup import CleanupRegistry
from core.runtime.fork import create_subagent_context, fork_context
import core.runtime.state as runtime_state
from core.runtime.state import AppState, BootstrapConfig, ToolUseContext


@pytest.fixture
def runtime_parent_bootstrap():
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


@pytest.fixture
def runtime_parent_tool_context(runtime_parent_bootstrap):
    app_state = AppState(turn_count=1, tool_overrides={"Bash": True})

    def set_app_state_for_tasks(updater):
        app_state.set_state(updater)

    return ToolUseContext(
        bootstrap=runtime_parent_bootstrap,
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


def test_bootstrap_config_minimal_creation():
    bc = BootstrapConfig(workspace_root=Path("/tmp"), model_name="claude-3-5-sonnet-20241022")
    assert bc.workspace_root == Path("/tmp")
    assert bc.project_root == Path("/tmp")
    assert bc.cwd == Path("/tmp")
    assert bc.model_name == "claude-3-5-sonnet-20241022"
    assert bc.api_key is None


def test_bootstrap_config_directory_lifetimes_can_be_distinct():
    bc = BootstrapConfig(
        workspace_root=Path("/workspace"),
        original_cwd=Path("/launcher"),
        project_root=Path("/workspace/project"),
        cwd=Path("/workspace/project/src"),
        model_name="test",
    )
    assert bc.original_cwd == Path("/launcher")
    assert bc.project_root == Path("/workspace/project")
    assert bc.cwd == Path("/workspace/project/src")
    assert bc.workspace_root == Path("/workspace")


def test_app_state_defaults_cover_permission_tracks():
    s = AppState()
    assert s.messages == []
    assert s.turn_count == 0
    assert s.total_cost == 0.0
    assert s.compact_boundary_index == 0
    assert s.tool_permission_context.alwaysAllowRules == {}
    assert s.tool_permission_context.alwaysDenyRules == {}
    assert s.tool_permission_context.alwaysAskRules == {}
    assert s.pending_permission_requests == {}
    assert s.resolved_permission_requests == {}


def test_app_state_session_hooks_can_be_added_and_removed_per_event():
    seen = []

    def start_hook(payload):
        seen.append(payload["event"])

    s = AppState()
    s.add_session_hook("SessionStart", start_hook)

    hooks = s.get_session_hooks("SessionStart")
    assert hooks == [start_hook]

    hooks[0]({"event": "SessionStart"})
    assert seen == ["SessionStart"]

    s.remove_session_hook("SessionStart", start_hook)
    assert s.get_session_hooks("SessionStart") == []


def test_tool_use_context_subagent_noop_set_state():
    bc = BootstrapConfig(workspace_root=Path("/tmp"), model_name="test")
    app_state = AppState(turn_count=5)
    calls = []
    noop = lambda _: calls.append("called")
    ctx = ToolUseContext(bootstrap=bc, get_app_state=lambda: app_state, set_app_state=noop)
    ctx.set_app_state(AppState(turn_count=99))
    assert len(calls) == 1
    assert app_state.turn_count == 5


def test_tool_use_context_core_callable_fields_are_not_typed_as_any():
    hints = get_type_hints(ToolUseContext, globalns=vars(runtime_state))

    assert hints["get_app_state"] is not Any
    assert hints["set_app_state"] is not Any
    assert hints["set_app_state_for_tasks"] is not Any
    assert hints["refresh_tools"] is not Any
    assert hints["can_use_tool"] is not Any
    assert hints["request_permission"] is not Any
    assert hints["consume_permission_resolution"] is not Any
    assert hints["abort_controller"] is not Any


def test_fork_context_copies_bootstrap_and_generates_new_session_id(runtime_parent_bootstrap):
    child = fork_context(runtime_parent_bootstrap)
    assert child.workspace_root == runtime_parent_bootstrap.workspace_root
    assert child.original_cwd == runtime_parent_bootstrap.original_cwd
    assert child.project_root == runtime_parent_bootstrap.project_root
    assert child.cwd == runtime_parent_bootstrap.cwd
    assert child.model_name == runtime_parent_bootstrap.model_name
    assert child.api_key == runtime_parent_bootstrap.api_key
    assert child.session_id != runtime_parent_bootstrap.session_id
    assert child.parent_session_id == runtime_parent_bootstrap.session_id


def test_create_subagent_context_keeps_parent_state_isolation(runtime_parent_tool_context):
    child = create_subagent_context(runtime_parent_tool_context)

    child.set_app_state(lambda prev: prev.model_copy(update={"turn_count": 9}))
    assert runtime_parent_tool_context.get_app_state().turn_count == 1

    child.set_app_state_for_tasks(lambda prev: prev.model_copy(update={"turn_count": 9}))
    assert runtime_parent_tool_context.get_app_state().turn_count == 9


def test_create_subagent_context_copies_read_state_and_abort_link(runtime_parent_tool_context):
    runtime_parent_tool_context.read_file_state = {
        "/tmp/readme.md": {"partial": False, "meta": {"seen": 1}}
    }
    runtime_parent_tool_context.abort_controller = AbortController()

    child = create_subagent_context(runtime_parent_tool_context)
    child.read_file_state["/tmp/readme.md"]["partial"] = True
    child.read_file_state["/tmp/readme.md"]["meta"]["seen"] = 9
    child.abort_controller.abort()

    assert runtime_parent_tool_context.read_file_state["/tmp/readme.md"] == {
        "partial": False,
        "meta": {"seen": 1},
    }
    assert runtime_parent_tool_context.abort_controller.is_aborted() is False


@pytest.mark.asyncio
async def test_cleanup_registry_runs_in_priority_order_and_survives_failures():
    order = []
    reg = CleanupRegistry()

    def failing():
        raise RuntimeError("boom")

    reg.register(lambda: order.append(3), priority=3)
    reg.register(failing, priority=1)
    reg.register(lambda: order.append(2), priority=2)
    await reg.run_cleanup()
    assert order == [2, 3]


@pytest.mark.asyncio
async def test_cleanup_registry_reuses_first_inflight_run():
    order = []
    release = asyncio.Event()
    reg = CleanupRegistry()

    async def slow():
        order.append("start")
        await release.wait()
        order.append("done")

    reg.register(slow, priority=1)

    first = asyncio.create_task(reg.run_cleanup())
    for _ in range(10):
        if order == ["start"]:
            break
        await asyncio.sleep(0)

    second = asyncio.create_task(reg.run_cleanup())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)

    assert order == ["start", "done"]


def test_cleanup_registry_register_returns_deregister_handle():
    order = []
    reg = CleanupRegistry()

    unregister = reg.register(lambda: order.append("gone"), priority=1)
    reg.register(lambda: order.append("kept"), priority=2)
    unregister()

    asyncio.run(reg.run_cleanup())
    assert order == ["kept"]


def test_cleanup_registry_installs_signal_handlers(monkeypatch):
    registered = []

    class _FakeLoop:
        def add_signal_handler(self, sig, handler):
            registered.append(sig)

    monkeypatch.setattr(asyncio, "get_event_loop", lambda: _FakeLoop())

    CleanupRegistry()

    expected = {signal.SIGINT, signal.SIGTERM}
    if hasattr(signal, "SIGHUP"):
        expected.add(signal.SIGHUP)

    assert set(registered) == expected
