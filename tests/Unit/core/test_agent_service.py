"""Unit tests for AgentService sub-agent boundaries and policy."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from core.agents.registry import AgentEntry, AgentRegistry
from core.agents.service import (
    AGENT_DISALLOWED,
    AGENT_SCHEMA,
    ASK_USER_QUESTION_SCHEMA,
    EXPLORE_ALLOWED,
    TASK_OUTPUT_SCHEMA,
    AgentService,
    _BashBackgroundRun,
    _resolve_subagent_model,
    _RunningTask,
)
from core.runtime.middleware import ToolCallRequest
from core.runtime.registry import ToolEntry, ToolRegistry
from core.runtime.runner import ToolRunner
from core.runtime.state import AppState, BootstrapConfig, ToolUseContext
from sandbox.manager import SandboxManager
from sandbox.providers.local import LocalSessionProvider
from sandbox.thread_context import get_current_thread_id, set_current_messages, set_current_thread_id


class _CapturingRegistry(ToolRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.last_entry: ToolEntry | None = None

    def register(self, entry: ToolEntry) -> None:
        self.last_entry = entry
        super().register(entry)


class _FakeAgentRegistry(AgentRegistry):
    def __init__(self) -> None:
        self._latest_by_name_parent: dict[tuple[str, str | None], AgentEntry] = {}

    async def register(self, entry):
        self.entry = entry

    async def update_status(self, agent_id: str, status: str):
        self.last_status = (agent_id, status)

    async def get_latest_by_name_and_parent(self, name: str, parent_agent_id: str | None):
        return self._latest_by_name_parent.get((name, parent_agent_id))


class _FakeThreadRepo:
    def __init__(self, rows: dict[str, dict] | None = None):
        self.rows = rows or {}
        self.created: list[dict] = []

    def get_by_id(self, thread_id: str):
        return self.rows.get(thread_id)

    def get_next_branch_index(self, agent_user_id: str) -> int:
        branch_indexes = [int(row["branch_index"]) for row in self.rows.values() if row["agent_user_id"] == agent_user_id]
        return (max(branch_indexes) if branch_indexes else 0) + 1

    def create(
        self,
        thread_id: str,
        agent_user_id: str,
        sandbox_type: str,
        cwd: str | None,
        created_at: float,
        **extra,
    ):
        row = {
            "id": thread_id,
            "agent_user_id": agent_user_id,
            "sandbox_type": sandbox_type,
            "cwd": cwd,
            "model": extra.get("model"),
            "is_main": bool(extra.get("is_main", False)),
            "branch_index": int(extra["branch_index"]),
            "created_at": created_at,
        }
        self.rows[thread_id] = row
        self.created.append(row)


class _FakeUserRepo:
    def __init__(self, names: dict[str, str]):
        self._names = names

    def get_by_id(self, user_id: str):
        name = self._names.get(user_id)
        if name is None:
            return None
        return SimpleNamespace(id=user_id, display_name=name, avatar=None)


class _FakeChildAgent:
    def __init__(self, workspace_root: Path, model_name: str):
        self.workspace_root = workspace_root
        self.model_name = model_name
        self._bootstrap = BootstrapConfig(workspace_root=workspace_root, model_name=model_name)
        self.apply_fork_calls: list[tuple[BootstrapConfig, ToolUseContext | None]] = []
        self.cleanup_calls = 0
        self.closed = False
        self.close_kwargs: dict[str, object] = {}
        self._agent_service = SimpleNamespace(
            _parent_bootstrap=None,
            _parent_tool_context=None,
            cleanup_background_runs=self._cleanup_background_runs,
        )
        self.agent = SimpleNamespace(astream=self._astream)

    async def ainit(self):
        return None

    async def _astream(self, *args, **kwargs):
        if False:
            yield None
        return

    async def _cleanup_background_runs(self):
        self.cleanup_calls += 1

    def close(self, **kwargs):
        self.closed = True
        self.close_kwargs = kwargs
        return None

    def apply_forked_child_context(
        self,
        bootstrap: BootstrapConfig,
        *,
        tool_context: ToolUseContext | None = None,
    ) -> None:
        self.apply_fork_calls.append((bootstrap, tool_context))
        self._bootstrap = bootstrap
        self.agent._bootstrap = bootstrap
        self._agent_service._parent_bootstrap = bootstrap
        if tool_context is not None:
            self._agent_service._parent_tool_context = tool_context
            self.agent._tool_abort_controller = tool_context.abort_controller


class _FakeAsyncCommand:
    def __init__(self):
        self.done = False
        self.stdout_buffer = []
        self.stderr_buffer = []
        self.exit_code = None
        self.process = SimpleNamespace(terminate=self._terminate, kill=self._kill, wait=self._wait)
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def _terminate(self):
        self.terminated = True
        self.done = True

    def _kill(self):
        self.killed = True
        self.done = True

    async def _wait(self):
        self.wait_calls += 1
        return 0


def _make_parent_context(tmp_path: Path, model_name: str = "gpt-parent") -> ToolUseContext:
    parent_state = AppState(turn_count=1)
    return ToolUseContext(
        bootstrap=BootstrapConfig(workspace_root=tmp_path, model_name=model_name),
        get_app_state=parent_state.get_state,
        set_app_state=parent_state.set_state,
        set_app_state_for_tasks=parent_state.set_state,
        read_file_state={"/tmp/readme.md": {"partial": False}},
        loaded_nested_memory_paths={"/tmp/memory.md"},
        discovered_skill_names={"skill-a"},
        nested_memory_attachment_triggers={"turn-a"},
        messages=["hello"],
    )


def _make_tool_request(
    name: str,
    args: dict[str, object],
    *,
    state: ToolUseContext,
    call_id: str = "tc-1",
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": call_id},
        state=state,
    )


def _make_service(tmp_path: Path, **kwargs) -> AgentService:
    tool_registry = kwargs.pop("tool_registry", None) or _CapturingRegistry()
    agent_registry = kwargs.pop("agent_registry", None) or _FakeAgentRegistry()
    model_name = kwargs.pop("model_name", "gpt-test")
    return AgentService(
        tool_registry=tool_registry,
        agent_registry=agent_registry,
        workspace_root=tmp_path,
        model_name=model_name,
        **kwargs,
    )


def _agent_tool_json(result) -> dict[str, Any]:
    content = getattr(result, "content", result)
    assert isinstance(content, str)
    return json.loads(content)


def _patch_create_leon_agent(
    monkeypatch: pytest.MonkeyPatch,
    *,
    child_cls=_FakeChildAgent,
    created: list[_FakeChildAgent] | None = None,
    captured: dict[str, Any] | None = None,
) -> None:
    def fake_create_leon_agent(*, model_name, workspace_root, **kwargs):
        child = child_cls(Path(workspace_root), model_name)
        if created is not None:
            created.append(child)
        if captured is not None:
            captured["model_name"] = model_name
            captured["workspace_root"] = Path(workspace_root)
            captured["kwargs"] = kwargs
        return child

    monkeypatch.setattr("core.runtime.agent.create_leon_agent", fake_create_leon_agent)


async def _sleep_forever():
    while True:
        await asyncio.sleep(3600)


@pytest.mark.asyncio
async def test_task_output_reports_running_command_honestly(tmp_path):
    service = _make_service(tmp_path)
    async_cmd = _FakeAsyncCommand()
    service._tasks["cmd_test123"] = _BashBackgroundRun(async_cmd, "echo hello")

    payload = json.loads(await service._handle_task_output("cmd_test123", block=False))

    assert payload == {
        "task_id": "cmd_test123",
        "status": "running",
        "message": "Command is still running.",
    }


@pytest.mark.asyncio
async def test_task_output_keeps_agent_running_message_for_agent_tasks(tmp_path):
    service = _make_service(tmp_path)
    task = asyncio.create_task(_sleep_forever())
    service._tasks["task_agent123"] = _RunningTask(
        task=task,
        agent_id="agent-1",
        thread_id="thread-1",
    )

    try:
        payload = json.loads(await service._handle_task_output("task_agent123", block=False))
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert payload == {
        "task_id": "task_agent123",
        "status": "running",
        "message": "Agent is still running.",
    }


@pytest.mark.asyncio
async def test_task_output_times_out_when_blocking_wait_expires(tmp_path):
    service = _make_service(tmp_path)
    task = asyncio.create_task(_sleep_forever())
    service._tasks["task_agent123"] = _RunningTask(
        task=task,
        agent_id="agent-1",
        thread_id="thread-1",
    )

    try:
        payload = json.loads(await service._handle_task_output("task_agent123", timeout=1))
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert payload == {
        "task_id": "task_agent123",
        "status": "timeout",
        "message": "Agent is still running.",
    }


@pytest.mark.asyncio
async def test_task_output_reports_cancelled_bash_run_honestly(tmp_path):
    service = _make_service(tmp_path)
    async_cmd = _FakeAsyncCommand()
    async_cmd.done = True
    async_cmd.cancelled = True
    service._tasks["cmd_cancelled"] = _BashBackgroundRun(async_cmd, "sleep 20")

    payload = json.loads(await service._handle_task_output("cmd_cancelled", block=False))

    assert payload == {
        "task_id": "cmd_cancelled",
        "status": "cancelled",
        "result": "Command cancelled",
    }


@pytest.mark.asyncio
async def test_run_agent_applies_forked_bootstrap_to_child_agent(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []
    _patch_create_leon_agent(monkeypatch, created=created)

    service = _make_service(tmp_path)
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
    _patch_create_leon_agent(monkeypatch, created=created)

    service = _make_service(tmp_path)
    parent_context = _make_parent_context(tmp_path)

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
async def test_run_agent_uses_explicit_child_fork_wiring_api(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []
    _patch_create_leon_agent(monkeypatch, created=created)

    service = _make_service(tmp_path)
    parent_context = _make_parent_context(tmp_path)

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
    assert len(created[0].apply_fork_calls) == 1
    applied_bootstrap, applied_context = created[0].apply_fork_calls[0]
    assert applied_bootstrap is created[0]._bootstrap
    assert applied_context is created[0]._agent_service._parent_tool_context


@pytest.mark.asyncio
async def test_run_agent_uses_injected_child_agent_factory(tmp_path):
    created: list[_FakeChildAgent] = []

    def fake_child_agent_factory(*, model_name, workspace_root, **kwargs):
        child = _FakeChildAgent(Path(workspace_root), model_name)
        created.append(child)
        return child

    service = _make_service(tmp_path, child_agent_factory=fake_child_agent_factory)

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
    assert len(created) == 1


@pytest.mark.asyncio
async def test_agent_tool_fork_context_uses_parent_tool_context_messages(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    class _CapturingChild(_FakeChildAgent):
        async def _astream(self, payload, *args, **kwargs):
            captured["messages"] = payload["messages"]
            if False:
                yield None
            return

    _patch_create_leon_agent(monkeypatch, child_cls=_CapturingChild)

    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry)
    runner = ToolRunner(registry=registry)
    request = _make_tool_request(
        "Agent",
        {"prompt": "inspect", "description": "inspect workspace", "fork_context": True},
        state=_make_parent_context(tmp_path),
    )

    result = await runner.awrap_tool_call(request, AsyncMock())

    assert result.content == "(Agent completed with no text output)"
    assert captured["messages"] == [
        "hello",
        {
            "role": "user",
            "content": (
                "\n\n### ENTERING SUB-AGENT ROUTINE ###\n"
                "Messages above are from the parent thread (read-only context).\n"
                "Only complete the specific task assigned below.\n\n"
                "inspect"
            ),
        },
    ]


@pytest.mark.asyncio
async def test_agent_tool_fork_context_treats_empty_parent_messages_as_authoritative(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    class _CapturingChild(_FakeChildAgent):
        async def _astream(self, payload, *args, **kwargs):
            captured["messages"] = payload["messages"]
            if False:
                yield None
            return

    _patch_create_leon_agent(monkeypatch, child_cls=_CapturingChild)
    set_current_messages([{"role": "user", "content": "AMBIENT_LEAK"}])

    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry)
    runner = ToolRunner(registry=registry)
    parent_context = _make_parent_context(tmp_path)
    parent_context.messages = []
    request = _make_tool_request(
        "Agent",
        {"prompt": "inspect", "description": "inspect workspace", "fork_context": True},
        state=parent_context,
    )

    result = await runner.awrap_tool_call(request, AsyncMock())

    assert result.content == "(Agent completed with no text output)"
    assert captured["messages"] == [
        {
            "role": "user",
            "content": (
                "\n\n### ENTERING SUB-AGENT ROUTINE ###\n"
                "Messages above are from the parent thread (read-only context).\n"
                "Only complete the specific task assigned below.\n\n"
                "inspect"
            ),
        },
    ]


@pytest.mark.asyncio
async def test_run_agent_rolls_child_bootstrap_costs_back_into_parent_bootstrap(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []

    class _CostReportingChild(_FakeChildAgent):
        async def _astream(self, *args, **kwargs):
            self._bootstrap.total_cost_usd = 9.75
            self._bootstrap.total_tool_duration_ms = 222
            if False:
                yield None
            return

    _patch_create_leon_agent(monkeypatch, child_cls=_CostReportingChild, created=created)

    service = _make_service(tmp_path)
    service._parent_bootstrap = BootstrapConfig(
        workspace_root=Path("/workspace"),
        model_name="gpt-parent",
        total_cost_usd=1.5,
        total_tool_duration_ms=77,
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
    assert created[0]._bootstrap.total_cost_usd == 9.75
    assert created[0]._bootstrap.total_tool_duration_ms == 222
    assert service._parent_bootstrap is not None
    assert service._parent_bootstrap.total_cost_usd == 9.75
    assert service._parent_bootstrap.total_tool_duration_ms == 222


@pytest.mark.asyncio
async def test_run_agent_preserves_concurrent_parent_and_child_bootstrap_growth(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []

    class _ConcurrentCostChild(_FakeChildAgent):
        async def _astream(self, *args, **kwargs):
            assert service._parent_bootstrap is not None
            service._parent_bootstrap.total_cost_usd = 2.0
            service._parent_bootstrap.total_tool_duration_ms = 20
            self._bootstrap.total_cost_usd = 1.5
            self._bootstrap.total_tool_duration_ms = 15
            if False:
                yield None
            return

    _patch_create_leon_agent(monkeypatch, child_cls=_ConcurrentCostChild, created=created)

    service = _make_service(tmp_path)
    service._parent_bootstrap = BootstrapConfig(
        workspace_root=Path("/workspace"),
        model_name="gpt-parent",
        total_cost_usd=1.0,
        total_tool_duration_ms=10,
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
    assert created[0]._bootstrap.total_cost_usd == 1.5
    assert created[0]._bootstrap.total_tool_duration_ms == 15
    assert service._parent_bootstrap.total_cost_usd == 2.5
    assert service._parent_bootstrap.total_tool_duration_ms == 25


@pytest.mark.asyncio
async def test_agent_tool_live_runner_path_passes_isolated_tool_context_to_child(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []
    _patch_create_leon_agent(monkeypatch, created=created)

    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry)
    runner = ToolRunner(registry=registry)
    parent_context = _make_parent_context(tmp_path)
    request = _make_tool_request(
        "Agent",
        {"prompt": "do work", "description": "do work"},
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
async def test_run_agent_without_fork_context_does_not_inject_parent_messages(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    class _CapturingChild(_FakeChildAgent):
        async def _astream(self, payload, *args, **kwargs):
            captured["messages"] = payload["messages"]
            if False:
                yield None
            return

    _patch_create_leon_agent(monkeypatch, child_cls=_CapturingChild)

    service = _make_service(tmp_path)
    parent_context = _make_parent_context(tmp_path)
    parent_context.messages = [
        {
            "role": "user",
            "content": "PARENT_CONTROL_PROMPT",
        }
    ]

    result = await service._run_agent(
        task_id="task-1",
        agent_name="child",
        thread_id="subagent-1",
        prompt="child task only",
        subagent_type="general",
        max_turns=None,
        fork_context=False,
        parent_tool_context=parent_context,
    )

    assert result == "(Agent completed with no text output)"
    assert captured["messages"] == [{"role": "user", "content": "child task only"}]


@pytest.mark.asyncio
async def test_run_agent_child_tool_context_deep_clones_read_file_state(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []
    _patch_create_leon_agent(monkeypatch, created=created)

    service = _make_service(tmp_path)
    parent_context = _make_parent_context(tmp_path)
    parent_context.read_file_state = {"/tmp/readme.md": {"partial": False, "meta": {"seen": 1}}}

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


@pytest.mark.asyncio
async def test_agent_tool_live_runner_path_applies_role_specific_tool_filters(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}
    _patch_create_leon_agent(monkeypatch, captured=captured)

    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry, model_name="gpt-parent")
    runner = ToolRunner(registry=registry)
    request = _make_tool_request(
        "Agent",
        {"prompt": "inspect", "description": "inspect workspace", "subagent_type": "explore"},
        state=_make_parent_context(tmp_path, model_name="gpt-parent"),
    )

    result = await runner.awrap_tool_call(request, AsyncMock())

    assert result.content == "(Agent completed with no text output)"
    assert captured["model_name"] == "gpt-parent"
    assert captured["kwargs"]["agent"] == "explore"
    assert captured["kwargs"]["allowed_tools"] == EXPLORE_ALLOWED
    assert captured["kwargs"]["extra_blocked_tools"] == AGENT_DISALLOWED


@pytest.mark.asyncio
async def test_agent_tool_model_priority_prefers_env_over_tool_frontmatter_and_parent(monkeypatch, tmp_path):
    agent_dir = tmp_path / ".leon" / "agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "explore.md").write_text(
        "---\nname: explore\nmodel: frontmatter-model\ntools:\n  - Read\n---\nfrontmatter prompt\n",
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}
    _patch_create_leon_agent(monkeypatch, captured=captured)
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL", "env-model")

    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry, model_name="parent-model")
    runner = ToolRunner(registry=registry)
    request = _make_tool_request(
        "Agent",
        {
            "prompt": "inspect",
            "description": "inspect workspace",
            "subagent_type": "explore",
            "model": "tool-model",
        },
        state=_make_parent_context(tmp_path, model_name="parent-model"),
    )

    await runner.awrap_tool_call(request, AsyncMock())

    assert captured["model_name"] == "env-model"
    assert captured["kwargs"]["agent"] == "explore"


def test_resolve_subagent_model_ignores_member_dir_frontmatter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home_root = tmp_path
    monkeypatch.setattr("config.loader.user_home_read_candidates", lambda *parts: (home_root.joinpath(*parts),))
    member_dir = home_root / "members" / "explore"
    member_dir.mkdir(parents=True)
    (member_dir / "agent.md").write_text(
        "---\nname: explore\nmodel: member-model\ntools:\n  - Read\n---\nmember prompt\n",
        encoding="utf-8",
    )

    resolved = _resolve_subagent_model(
        workspace_root=tmp_path,
        subagent_type="explore",
        requested_model=None,
        inherited_model="parent-model",
    )

    assert resolved == "parent-model"


@pytest.mark.asyncio
async def test_agent_tool_model_priority_prefers_tool_over_frontmatter_and_parent(monkeypatch, tmp_path):
    agent_dir = tmp_path / ".leon" / "agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "explore.md").write_text(
        "---\nname: explore\nmodel: frontmatter-model\ntools:\n  - Read\n---\nfrontmatter prompt\n",
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}
    _patch_create_leon_agent(monkeypatch, captured=captured)

    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry, model_name="parent-model")
    runner = ToolRunner(registry=registry)
    request = _make_tool_request(
        "Agent",
        {
            "prompt": "inspect",
            "description": "inspect workspace",
            "subagent_type": "explore",
            "model": "tool-model",
        },
        state=_make_parent_context(tmp_path, model_name="parent-model"),
    )

    await runner.awrap_tool_call(request, AsyncMock())

    assert captured["model_name"] == "tool-model"
    assert captured["kwargs"]["agent"] == "explore"


@pytest.mark.asyncio
async def test_agent_tool_model_default_literal_inherits_parent_model(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}
    _patch_create_leon_agent(monkeypatch, captured=captured)

    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry, model_name="parent-model")
    runner = ToolRunner(registry=registry)
    request = _make_tool_request(
        "Agent",
        {
            "prompt": "inspect",
            "description": "inspect workspace",
            "subagent_type": "explore",
            "model": "default",
        },
        state=_make_parent_context(tmp_path, model_name="parent-model"),
    )

    await runner.awrap_tool_call(request, AsyncMock())

    assert captured["model_name"] == "parent-model"
    assert captured["kwargs"]["agent"] == "explore"


@pytest.mark.asyncio
async def test_agent_tool_model_inherit_literal_inherits_parent_model(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}
    _patch_create_leon_agent(monkeypatch, captured=captured)

    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry, model_name="parent-model")
    runner = ToolRunner(registry=registry)
    request = _make_tool_request(
        "Agent",
        {
            "prompt": "inspect",
            "description": "inspect workspace",
            "subagent_type": "explore",
            "model": "inherit",
        },
        state=_make_parent_context(tmp_path, model_name="parent-model"),
    )

    await runner.awrap_tool_call(request, AsyncMock())

    assert captured["model_name"] == "parent-model"
    assert captured["kwargs"]["agent"] == "explore"


@pytest.mark.asyncio
async def test_agent_tool_inherited_default_bootstrap_model_uses_parent_service_model(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}
    _patch_create_leon_agent(monkeypatch, captured=captured)

    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry, model_name="parent-service-model")
    runner = ToolRunner(registry=registry)
    request = _make_tool_request(
        "Agent",
        {"prompt": "inspect", "description": "inspect workspace", "subagent_type": "explore"},
        state=_make_parent_context(tmp_path, model_name="default"),
    )

    await runner.awrap_tool_call(request, AsyncMock())

    assert captured["model_name"] == "parent-service-model"
    assert captured["kwargs"]["agent"] == "explore"


@pytest.mark.asyncio
async def test_agent_tool_model_priority_prefers_frontmatter_over_parent(monkeypatch, tmp_path):
    agent_dir = tmp_path / ".leon" / "agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "explore.md").write_text(
        "---\nname: explore\nmodel: frontmatter-model\ntools:\n  - Read\n---\nfrontmatter prompt\n",
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}
    _patch_create_leon_agent(monkeypatch, captured=captured)

    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry, model_name="parent-model")
    runner = ToolRunner(registry=registry)
    request = _make_tool_request(
        "Agent",
        {"prompt": "inspect", "description": "inspect workspace", "subagent_type": "explore"},
        state=_make_parent_context(tmp_path, model_name="parent-model"),
    )

    await runner.awrap_tool_call(request, AsyncMock())

    assert captured["model_name"] == "frontmatter-model"
    assert captured["kwargs"]["agent"] == "explore"


@pytest.mark.asyncio
async def test_agent_tool_model_priority_inherits_parent_when_no_env_tool_or_frontmatter(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}
    _patch_create_leon_agent(monkeypatch, captured=captured)

    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry, model_name="service-model")
    runner = ToolRunner(registry=registry)
    request = _make_tool_request(
        "Agent",
        {"prompt": "inspect", "description": "inspect workspace", "subagent_type": "explore"},
        state=_make_parent_context(tmp_path, model_name="parent-model"),
    )

    await runner.awrap_tool_call(request, AsyncMock())

    assert captured["model_name"] == "parent-model"
    assert captured["kwargs"]["agent"] == "explore"


@pytest.mark.asyncio
async def test_cleanup_background_runs_cancels_pending_agent_and_shell_runs(tmp_path):
    service = _make_service(tmp_path)
    agent_task = asyncio.create_task(_sleep_forever())
    shell_cmd = _FakeAsyncCommand()
    service._tasks["agent-task"] = _RunningTask(
        task=agent_task,
        agent_id="agent-task",
        thread_id="subagent-agent-task",
        description="agent task",
    )
    service._tasks["bash-task"] = _BashBackgroundRun(
        async_cmd=shell_cmd,
        command="sleep 999",
        description="bash task",
    )

    await service.cleanup_background_runs()

    assert agent_task.cancelled() is True
    assert shell_cmd.terminated is True
    assert shell_cmd.wait_calls == 1
    assert service._tasks == {}


@pytest.mark.asyncio
async def test_cleanup_background_runs_does_not_relabel_completed_agent_run(tmp_path):
    registry = _FakeAgentRegistry()
    service = _make_service(tmp_path, agent_registry=registry)
    completed_task = asyncio.create_task(asyncio.sleep(0, result="done"))
    await completed_task
    service._tasks["agent-task"] = _RunningTask(
        task=completed_task,
        agent_id="agent-task",
        thread_id="subagent-agent-task",
        description="agent task",
    )

    await service.cleanup_background_runs()

    assert getattr(registry, "last_status", None) is None
    assert service._tasks == {}


@pytest.mark.asyncio
async def test_run_agent_cleans_up_child_background_runs_before_close(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []
    _patch_create_leon_agent(monkeypatch, created=created)

    service = _make_service(tmp_path)

    result = await service._run_agent(
        task_id="task-1",
        agent_name="child",
        thread_id="subagent-task-1",
        prompt="hello",
        subagent_type="explore",
        max_turns=None,
    )

    assert result == "(Agent completed with no text output)"
    assert created[0].cleanup_calls == 1
    assert created[0].closed is True


@pytest.mark.asyncio
async def test_run_agent_links_child_abort_controller_to_parent_tool_context(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []
    _patch_create_leon_agent(monkeypatch, created=created)

    service = _make_service(tmp_path)
    parent_context = _make_parent_context(tmp_path)

    result = await service._run_agent(
        task_id="task-1",
        agent_name="child",
        thread_id="subagent-task-1",
        prompt="hello",
        subagent_type="explore",
        max_turns=None,
        parent_tool_context=parent_context,
    )

    assert result == "(Agent completed with no text output)"

    child_context = created[0]._agent_service._parent_tool_context
    assert child_context is not None
    assert getattr(created[0].agent, "_tool_abort_controller", None) is child_context.abort_controller

    parent_context.abort_controller.abort()

    assert child_context.abort_controller.is_aborted() is True


@pytest.mark.asyncio
async def test_run_agent_reuses_parent_lease_for_child_thread_terminal(monkeypatch, tmp_path, temp_db):
    created: list[_FakeChildAgent] = []
    observed: dict[str, str] = {}
    parent_thread_id = "parent-thread"
    child_thread_id = "subagent-child"

    manager = SandboxManager(
        provider=LocalSessionProvider(default_cwd=str(tmp_path)),
        db_path=temp_db,
    )
    monkeypatch.setenv("LEON_SANDBOX_DB_PATH", str(temp_db))
    monkeypatch.setattr("sandbox.resource_snapshot.upsert_lease_resource_snapshot", lambda **_kwargs: None)
    monkeypatch.setattr(manager, "_setup_mounts", lambda thread_id: {"source": object(), "remote_path": str(tmp_path)})
    monkeypatch.setattr(manager, "_sync_to_sandbox", lambda *args, **kwargs: None)

    parent_capability = manager.get_sandbox(parent_thread_id)
    parent_terminal_id = parent_capability._session.terminal.terminal_id
    parent_lease_id = parent_capability._session.lease.lease_id

    class _LeaseCapturingChild(_FakeChildAgent):
        async def _astream(self, *args, **kwargs):
            current_thread_id = get_current_thread_id()
            assert current_thread_id is not None
            child_capability = manager.get_sandbox(current_thread_id)
            observed["child_terminal_id"] = child_capability._session.terminal.terminal_id
            observed["child_lease_id"] = child_capability._session.lease.lease_id
            if False:
                yield None
            return

    _patch_create_leon_agent(monkeypatch, child_cls=_LeaseCapturingChild, created=created)
    set_current_thread_id(parent_thread_id)

    service = _make_service(tmp_path)

    try:
        result = await service._run_agent(
            task_id="task-1",
            agent_name="child",
            thread_id=child_thread_id,
            prompt="hello",
            subagent_type="explore",
            max_turns=None,
        )

        assert result == "(Agent completed with no text output)"
        assert created
        assert observed["child_terminal_id"] != parent_terminal_id
        assert observed["child_lease_id"] == parent_lease_id
    finally:
        manager.close()


@pytest.mark.asyncio
async def test_run_agent_inherits_parent_sandbox_when_forking_child(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}
    _patch_create_leon_agent(monkeypatch, captured=captured)

    service = _make_service(tmp_path)
    service._parent_bootstrap = BootstrapConfig(
        workspace_root=Path("/home/daytona"),
        original_cwd=Path("/home/daytona"),
        project_root=Path("/home/daytona"),
        cwd=Path("/home/daytona"),
        model_name="gpt-parent",
        sandbox_type="daytona_selfhost",
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
    assert captured["workspace_root"] == Path("/home/daytona")
    assert captured["kwargs"]["sandbox"] == "daytona_selfhost"


@pytest.mark.asyncio
async def test_run_agent_child_cleanup_skips_sandbox_close(monkeypatch, tmp_path):
    created: list[_FakeChildAgent] = []
    _patch_create_leon_agent(monkeypatch, created=created)

    service = _make_service(tmp_path)

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
    assert created[0].closed is True
    assert created[0].close_kwargs == {"cleanup_sandbox": False}


@pytest.mark.asyncio
async def test_handle_agent_registers_subagent_thread_metadata_before_return(monkeypatch, tmp_path):
    _patch_create_leon_agent(monkeypatch)

    thread_repo = _FakeThreadRepo(
        rows={
            "parent-thread": {
                "id": "parent-thread",
                "agent_user_id": "agent-user-1",
                "sandbox_type": "daytona_selfhost",
                "cwd": "/home/daytona",
                "model": "gpt-parent",
                "is_main": True,
                "branch_index": 0,
                "created_at": 1.0,
            }
        }
    )
    user_repo = _FakeUserRepo({"agent-user-1": "Toad"})
    service = _make_service(
        tmp_path,
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    set_current_thread_id("parent-thread")
    try:
        raw = await service._handle_agent(
            prompt="do work",
            name="worker-1",
            run_in_background=True,
        )
        payload = _agent_tool_json(raw)
        child_thread_id = payload["thread_id"]

        child_thread = thread_repo.get_by_id(child_thread_id)

        assert child_thread is not None
        assert child_thread["agent_user_id"] == "agent-user-1"
        assert child_thread["sandbox_type"] == "daytona_selfhost"
        assert child_thread["cwd"] == "/home/daytona"
        assert child_thread["is_main"] is False
        assert child_thread["branch_index"] == 1
    finally:
        await service.cleanup_background_runs()
        set_current_thread_id("")


@pytest.mark.asyncio
async def test_handle_agent_reuses_existing_completed_child_thread_for_same_parent_and_name(monkeypatch, tmp_path):
    _patch_create_leon_agent(monkeypatch)

    thread_repo = _FakeThreadRepo(
        rows={
            "parent-thread": {
                "id": "parent-thread",
                "agent_user_id": "agent-user-1",
                "sandbox_type": "daytona_selfhost",
                "cwd": "/home/daytona",
                "model": "gpt-parent",
                "is_main": True,
                "branch_index": 0,
                "created_at": 1.0,
            },
            "subagent-existing": {
                "id": "subagent-existing",
                "agent_user_id": "agent-user-1",
                "sandbox_type": "daytona_selfhost",
                "cwd": "/home/daytona",
                "model": "gpt-test",
                "is_main": False,
                "branch_index": 1,
                "created_at": 2.0,
            },
        }
    )
    registry = _FakeAgentRegistry()
    registry._latest_by_name_parent[("worker-1", "parent-thread")] = AgentEntry(
        agent_id="old-agent",
        name="worker-1",
        thread_id="subagent-existing",
        status="completed",
        parent_agent_id="parent-thread",
        subagent_type="general",
    )
    service = _make_service(
        tmp_path,
        agent_registry=registry,
        thread_repo=thread_repo,
        user_repo=_FakeUserRepo({"agent-user-1": "Toad"}),
    )

    set_current_thread_id("parent-thread")
    try:
        raw = await service._handle_agent(
            prompt="continue work",
            name="worker-1",
            run_in_background=True,
        )

        payload = _agent_tool_json(raw)
        assert payload["thread_id"] == "subagent-existing"
        assert len(thread_repo.created) == 0
    finally:
        await service.cleanup_background_runs()
        set_current_thread_id("")


@pytest.mark.asyncio
async def test_agent_tool_blocking_result_preserves_child_identity_metadata(monkeypatch, tmp_path):
    _patch_create_leon_agent(monkeypatch)

    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry)
    runner = ToolRunner(registry=registry)
    request = _make_tool_request(
        "Agent",
        {"prompt": "inspect", "description": "inspect workspace"},
        state=_make_parent_context(tmp_path),
    )

    result = await runner.awrap_tool_call(request, AsyncMock())

    meta = result.additional_kwargs["tool_result_meta"]
    assert meta["task_id"]
    assert meta["subagent_thread_id"].startswith("subagent-")


@pytest.mark.asyncio
async def test_run_agent_uses_live_child_thread_bridge_when_web_app_present(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    async def fake_run_child_thread_live(agent, thread_id, prompt, app, *, input_messages):
        captured["agent"] = agent
        captured["thread_id"] = thread_id
        captured["prompt"] = prompt
        captured["app"] = app
        captured["input_messages"] = input_messages
        return "LIVE_CHILD_DONE"

    _patch_create_leon_agent(monkeypatch, captured=captured)
    monkeypatch.setattr("backend.web.services.streaming_service.run_child_thread_live", fake_run_child_thread_live)

    web_app = SimpleNamespace()
    service = _make_service(tmp_path, web_app=web_app)

    result = await service._run_agent(
        task_id="task-1",
        agent_name="child",
        thread_id="subagent-1",
        prompt="do work",
        subagent_type="general",
        max_turns=None,
        fork_context=False,
    )

    assert result == "LIVE_CHILD_DONE"
    assert captured["thread_id"] == "subagent-1"
    assert captured["prompt"] == "do work"
    assert captured["app"] is web_app
    assert captured["kwargs"]["web_app"] is web_app
    assert len(captured["input_messages"]) == 1
    assert captured["input_messages"][0]["role"] == "user"
    assert captured["input_messages"][0]["content"] == "do work"
    assert captured["agent"].cleanup_calls == 1
    assert captured["agent"].closed is False


@pytest.mark.asyncio
async def test_run_agent_normalizes_workspace_suffix_in_child_prompt(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    async def fake_run_child_thread_live(agent, thread_id, prompt, app, *, input_messages):
        captured["prompt"] = prompt
        captured["input_messages"] = input_messages
        return "LIVE_CHILD_DONE"

    _patch_create_leon_agent(monkeypatch)
    monkeypatch.setattr("backend.web.services.streaming_service.run_child_thread_live", fake_run_child_thread_live)

    service = _make_service(tmp_path, web_app=SimpleNamespace())
    raw_prompt = f"Inspect the workspace at {tmp_path}/current working directory. Read-only only. Report existing files."

    result = await service._run_agent(
        task_id="task-1",
        agent_name="child",
        thread_id="subagent-1",
        prompt=raw_prompt,
        subagent_type="general",
        max_turns=None,
        fork_context=False,
    )

    assert result == "LIVE_CHILD_DONE"
    expected_prompt = f"Inspect the workspace at {tmp_path}. Read-only only. Report existing files."
    assert captured["prompt"] == expected_prompt
    assert captured["input_messages"][0]["content"] == expected_prompt


def test_agent_schema_does_not_claim_general_has_full_tool_access():
    description = AGENT_SCHEMA["description"]

    assert "general (full tool access)" not in description
    assert "general (broad tool access except Agent, TaskOutput, and TaskStop)" in description


def test_agent_schema_requires_description():
    assert AGENT_SCHEMA["parameters"]["required"] == ["prompt", "description"]


def test_task_output_schema_exposes_block_and_timeout():
    properties = TASK_OUTPUT_SCHEMA["parameters"]["properties"]

    assert properties["block"]["default"] is True
    assert properties["timeout"]["default"] == 30000
    assert properties["timeout"]["maximum"] == 600000


@pytest.mark.asyncio
async def test_ask_user_question_requests_structured_question_payload(tmp_path):
    registry = ToolRegistry()
    _make_service(tmp_path, tool_registry=registry)
    runner = ToolRunner(registry=registry)
    app_state = AppState()
    captured: dict[str, Any] = {}

    def request_permission(name, args, context, request, message):
        captured["name"] = name
        captured["args"] = dict(args)
        captured["message"] = message
        return {"request_id": "ask-1"}

    request = _make_tool_request(
        "AskUserQuestion",
        {
            "questions": [
                {
                    "header": "Color",
                    "question": "Which color should I use?",
                    "options": [
                        {"label": "Blue", "description": "Use blue"},
                        {"label": "Green", "description": "Use green"},
                    ],
                }
            ]
        },
        state=ToolUseContext(
            bootstrap=BootstrapConfig(workspace_root=tmp_path, model_name="gpt-test"),
            get_app_state=app_state.get_state,
            set_app_state=app_state.set_state,
            request_permission=request_permission,
        ),
    )

    result = await runner.awrap_tool_call(request, AsyncMock())

    meta = result.additional_kwargs["tool_result_meta"]
    assert meta["kind"] == "permission_request"
    assert meta["request_id"] == "ask-1"
    assert result.content == "User input required to continue."
    assert captured["name"] == "AskUserQuestion"
    assert captured["message"] == "Please answer the following questions so Leon can continue."
    assert captured["args"] == {
        "questions": [
            {
                "header": "Color",
                "question": "Which color should I use?",
                "options": [
                    {"label": "Blue", "description": "Use blue"},
                    {"label": "Green", "description": "Use green"},
                ],
            }
        ]
    }


def test_ask_user_question_schema_requires_questions():
    assert ASK_USER_QUESTION_SCHEMA["parameters"]["required"] == ["questions"]
