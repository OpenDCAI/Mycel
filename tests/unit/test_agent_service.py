"""Unit tests for AgentService sub-agent fork boundaries."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.agents.service import AgentService
from core.runtime.registry import ToolRegistry
from core.runtime.runner import ToolRunner
from core.runtime.state import AppState, BootstrapConfig, ToolUseContext


class _FakeRegistry:
    def register(self, entry):
        self.last_entry = entry


class _FakeAgentRegistry:
    async def register(self, entry):
        self.entry = entry

    async def update_status(self, agent_id: str, status: str):
        self.last_status = (agent_id, status)


class _FakeChildAgent:
    def __init__(self, workspace_root: Path, model_name: str):
        self.workspace_root = workspace_root
        self.model_name = model_name
        self._bootstrap = BootstrapConfig(workspace_root=workspace_root, model_name=model_name)
        self._agent_service = SimpleNamespace(_parent_bootstrap=None, _parent_tool_context=None)
        self.agent = SimpleNamespace(astream=self._astream)

    async def ainit(self):
        return None

    async def _astream(self, *args, **kwargs):
        if False:
            yield None
        return

    def close(self):
        return None


@pytest.mark.asyncio
async def test_run_agent_applies_forked_bootstrap_to_child_agent(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []

    def fake_create_leon_agent(*, model_name, workspace_root, **kwargs):
        child = _FakeChildAgent(Path(workspace_root), model_name)
        created.append(child)
        return child

    monkeypatch.setattr("core.runtime.agent.create_leon_agent", fake_create_leon_agent)

    service = AgentService(
        tool_registry=_FakeRegistry(),
        agent_registry=_FakeAgentRegistry(),
        workspace_root=tmp_path,
        model_name="gpt-test",
    )
    service._parent_bootstrap = BootstrapConfig(
        workspace_root=Path("/workspace"),
        original_cwd=Path("/launcher"),
        project_root=Path("/workspace/project"),
        cwd=Path("/workspace/project/src"),
        model_name="gpt-parent",
        api_key="sk-parent",
        extra_allowed_paths=["/shared"],
        total_cost_usd=1.5,
        total_tool_duration_ms=77,
        model_provider="openai",
        base_url="https://api.example.com/v1",
        context_limit=12345,
    )

    result = await service._run_agent(
        task_id="task-1",
        agent_name="child",
        thread_id="subagent-1",
        prompt="do work",
        subagent_type="general",
        max_turns=None,
        fork_context=False,
    )

    assert result == "(Agent completed with no text output)"
    child = created[0]
    assert child._bootstrap.original_cwd == Path("/launcher")
    assert child._bootstrap.project_root == Path("/workspace/project")
    assert child._bootstrap.cwd == Path("/workspace/project/src")
    assert child._bootstrap.extra_allowed_paths == ["/shared"]
    assert child._bootstrap.parent_session_id == service._parent_bootstrap.session_id
    assert child._bootstrap.session_id != service._parent_bootstrap.session_id
    assert child._bootstrap.total_cost_usd == 1.5
    assert child._bootstrap.total_tool_duration_ms == 77
    assert child._bootstrap.model_provider == "openai"
    assert child._bootstrap.base_url == "https://api.example.com/v1"
    assert child._bootstrap.context_limit == 12345


@pytest.mark.asyncio
async def test_run_agent_applies_isolated_tool_context_to_child_agent_service(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []

    def fake_create_leon_agent(*, model_name, workspace_root, **kwargs):
        child = _FakeChildAgent(Path(workspace_root), model_name)
        created.append(child)
        return child

    monkeypatch.setattr("core.runtime.agent.create_leon_agent", fake_create_leon_agent)

    service = AgentService(
        tool_registry=_FakeRegistry(),
        agent_registry=_FakeAgentRegistry(),
        workspace_root=tmp_path,
        model_name="gpt-test",
    )
    parent_state = AppState(turn_count=1)
    parent_context = ToolUseContext(
        bootstrap=BootstrapConfig(workspace_root=tmp_path, model_name="gpt-parent"),
        get_app_state=parent_state.get_state,
        set_app_state=parent_state.set_state,
        set_app_state_for_tasks=parent_state.set_state,
        read_file_state={"/tmp/readme.md": {"partial": False}},
        loaded_nested_memory_paths={"/tmp/memory.md"},
        discovered_skill_names={"skill-a"},
        nested_memory_attachment_triggers={"turn-a"},
        messages=["hello"],
    )

    result = await service._run_agent(
        task_id="task-1",
        agent_name="child",
        thread_id="subagent-1",
        prompt="do work",
        subagent_type="general",
        max_turns=None,
        fork_context=False,
        parent_tool_context=parent_context,
    )

    assert result == "(Agent completed with no text output)"
    child_context = created[0]._agent_service._parent_tool_context
    assert child_context is not None
    assert child_context is not parent_context
    assert child_context.bootstrap.parent_session_id == parent_context.bootstrap.session_id
    child_context.set_app_state(lambda prev: prev.model_copy(update={"turn_count": 9}))
    assert parent_context.get_app_state().turn_count == 1
    child_context.set_app_state_for_tasks(lambda prev: prev.model_copy(update={"turn_count": 9}))
    assert parent_context.get_app_state().turn_count == 9


@pytest.mark.asyncio
async def test_agent_tool_live_runner_path_passes_isolated_tool_context_to_child(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []

    def fake_create_leon_agent(*, model_name, workspace_root, **kwargs):
        child = _FakeChildAgent(Path(workspace_root), model_name)
        created.append(child)
        return child

    monkeypatch.setattr("core.runtime.agent.create_leon_agent", fake_create_leon_agent)

    registry = ToolRegistry()
    AgentService(
        tool_registry=registry,
        agent_registry=_FakeAgentRegistry(),
        workspace_root=tmp_path,
        model_name="gpt-test",
    )
    runner = ToolRunner(registry=registry)
    parent_state = AppState(turn_count=1)
    parent_context = ToolUseContext(
        bootstrap=BootstrapConfig(workspace_root=tmp_path, model_name="gpt-parent"),
        get_app_state=parent_state.get_state,
        set_app_state=parent_state.set_state,
        set_app_state_for_tasks=parent_state.set_state,
        read_file_state={"/tmp/readme.md": {"partial": False}},
        loaded_nested_memory_paths={"/tmp/memory.md"},
        discovered_skill_names={"skill-a"},
        nested_memory_attachment_triggers={"turn-a"},
        messages=["hello"],
    )
    request = SimpleNamespace(
        tool_call={"name": "Agent", "args": {"prompt": "do work"}, "id": "tc-1"},
        state=parent_context,
    )

    result = await runner.awrap_tool_call(request, AsyncMock())

    assert result.content == "(Agent completed with no text output)"
    child_context = created[0]._agent_service._parent_tool_context
    assert child_context is not None
    assert child_context.bootstrap.parent_session_id == parent_context.bootstrap.session_id
    child_context.set_app_state(lambda prev: prev.model_copy(update={"turn_count": 9}))
    assert parent_context.get_app_state().turn_count == 1


@pytest.mark.asyncio
async def test_run_agent_child_tool_context_deep_clones_read_file_state(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []

    def fake_create_leon_agent(*, model_name, workspace_root, **kwargs):
        child = _FakeChildAgent(Path(workspace_root), model_name)
        created.append(child)
        return child

    monkeypatch.setattr("core.runtime.agent.create_leon_agent", fake_create_leon_agent)

    service = AgentService(
        tool_registry=_FakeRegistry(),
        agent_registry=_FakeAgentRegistry(),
        workspace_root=tmp_path,
        model_name="gpt-test",
    )
    parent_state = AppState(turn_count=1)
    parent_context = ToolUseContext(
        bootstrap=BootstrapConfig(workspace_root=tmp_path, model_name="gpt-parent"),
        get_app_state=parent_state.get_state,
        set_app_state=parent_state.set_state,
        set_app_state_for_tasks=parent_state.set_state,
        read_file_state={"/tmp/readme.md": {"partial": False, "meta": {"seen": 1}}},
        loaded_nested_memory_paths={"/tmp/memory.md"},
        discovered_skill_names={"skill-a"},
        nested_memory_attachment_triggers={"turn-a"},
        messages=["hello"],
    )

    result = await service._run_agent(
        task_id="task-1",
        agent_name="child",
        thread_id="subagent-1",
        prompt="do work",
        subagent_type="general",
        max_turns=None,
        fork_context=False,
        parent_tool_context=parent_context,
    )

    assert result == "(Agent completed with no text output)"
    child_context = created[0]._agent_service._parent_tool_context
    child_context.read_file_state["/tmp/readme.md"]["partial"] = True
    child_context.read_file_state["/tmp/readme.md"]["meta"]["seen"] = 9
    assert parent_context.read_file_state["/tmp/readme.md"] == {
        "partial": False,
        "meta": {"seen": 1},
    }
