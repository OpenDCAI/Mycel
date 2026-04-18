"""Integration tests for background task cleanup across command/agent surfaces."""

import asyncio
import json
import shlex
import shutil
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from core.agents.registry import AgentEntry
from core.agents.service import AgentService, BackgroundRun, _BashBackgroundRun, _RunningTask, request_background_run_stop
from core.runtime.middleware.queue import MessageQueueManager
from core.runtime.middleware.queue.middleware import SteeringMiddleware
from core.runtime.registry import ToolRegistry
from core.tools.command.bash.executor import BashExecutor
from core.tools.command.service import CommandService
from core.tools.command.zsh.executor import ZshExecutor
from sandbox.thread_context import set_current_thread_id


def _require_bash_run(run: BackgroundRun) -> _BashBackgroundRun:
    assert isinstance(run, _BashBackgroundRun)
    return run


def _require_running_task(run: BackgroundRun) -> _RunningTask:
    assert isinstance(run, _RunningTask)
    return run


def _available_posix_background_executors() -> list[type]:
    executors: list[type] = []
    if shutil.which("bash") is not None:
        executors.append(BashExecutor)
    if shutil.which("zsh") is not None:
        executors.append(ZshExecutor)
    return executors


class _SlowChildAgent:
    def __init__(self, first_text: str, release_event: asyncio.Event, started_event: asyncio.Event):
        self._first_text = first_text
        self._release_event = release_event
        self._started_event = started_event
        self._agent_service = type(
            "_ChildService",
            (),
            {"cleanup_background_runs": self._cleanup_background_runs},
        )()
        self.agent = type("_InnerAgent", (), {"astream": self._astream})()
        self.closed = False

    async def ainit(self):
        return None

    async def _astream(self, *args, **kwargs):
        self._started_event.set()
        yield {"agent": {"messages": [AIMessage(content=self._first_text)]}}
        await self._release_event.wait()

    async def _cleanup_background_runs(self):
        return None

    def close(self):
        self.closed = True
        return None


class _CompleteChildAgent:
    def __init__(self, text: str):
        self._text = text
        self._agent_service = type(
            "_ChildService",
            (),
            {"cleanup_background_runs": self._cleanup_background_runs},
        )()
        self.agent = type("_InnerAgent", (), {"astream": self._astream})()
        self.closed = False

    async def ainit(self):
        return None

    async def _astream(self, *args, **kwargs):
        yield {"agent": {"messages": [AIMessage(content=self._text)]}}

    async def _cleanup_background_runs(self):
        return None

    def close(self):
        self.closed = True
        return None


class _FailingInitChildAgent:
    def __init__(self, error: Exception):
        self._error = error

    async def ainit(self):
        raise self._error


def _agent_tool_json(result) -> dict:
    content = getattr(result, "content", result)
    return json.loads(content)


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="bash background cleanup integration requires a Unix shell",
)
def test_taskstop_terminates_real_background_bash_run(tmp_path):
    async def run():
        registry = ToolRegistry()
        shared_runs: dict[str, BackgroundRun] = {}
        executor = BashExecutor(default_cwd=str(tmp_path))
        command_service = CommandService(
            registry=registry,
            workspace_root=tmp_path,
            executor=executor,
            background_runs=shared_runs,
        )
        agent_service = AgentService(
            tool_registry=registry,
            workspace_root=Path(tmp_path),
            model_name="gpt-test",
            shared_runs=shared_runs,
        )

        result = await command_service._execute_async(
            "sleep 30",
            str(tmp_path),
            30.0,
            description="integration bash cleanup",
        )
        assert "task_id:" in result
        assert len(shared_runs) == 1

        task_id, running = next(iter(shared_runs.items()))
        bash_run = _require_bash_run(running)
        assert running.is_done is False

        stop_result = await agent_service._handle_task_stop(task_id)

        assert stop_result == f"Task {task_id} cancelled"
        assert task_id not in shared_runs
        assert bash_run._cmd.process.returncode is not None

    asyncio.run(run())


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="bash background cleanup integration requires a Unix shell",
)
def test_request_background_run_stop_kills_real_shell_command_tree(tmp_path):
    async def run():
        executor = BashExecutor(default_cwd=str(tmp_path))
        async_cmd = await executor.execute_async(
            "sleep 2; echo NEVER_BACKGROUND_CANCEL_TREE",
            cwd=str(tmp_path),
        )
        running = _BashBackgroundRun(async_cmd, "sleep 2; echo NEVER_BACKGROUND_CANCEL_TREE")

        await request_background_run_stop(running)
        await asyncio.sleep(2.5)

        assert async_cmd.cancelled is True
        assert async_cmd.done is True
        assert async_cmd.exit_code not in (None, 0)
        assert "NEVER_BACKGROUND_CANCEL_TREE" not in "".join(async_cmd.stdout_buffer)

    asyncio.run(run())


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="nested-shell cancel truth integration requires Unix shells",
)
@pytest.mark.parametrize("executor_cls", _available_posix_background_executors(), ids=lambda cls: cls.shell_name)
def test_request_background_run_stop_prevents_nested_shell_late_write_side_effect(tmp_path, executor_cls):
    async def run():
        executor = executor_cls(default_cwd=str(tmp_path))
        target = tmp_path / f"{executor_cls.shell_name}_cancel_nested_write.txt"
        token = f"NESTED_CANCEL_{executor_cls.shell_name.upper()}"
        inner = f"sleep 2; printf {shlex.quote(token)} > {shlex.quote(str(target))}"
        command = f"sh -lc {shlex.quote(inner)}"
        async_cmd = await executor.execute_async(command, cwd=str(tmp_path))
        running = _BashBackgroundRun(async_cmd, command)

        await request_background_run_stop(running)
        await asyncio.sleep(2.5)

        assert async_cmd.cancelled is True
        assert async_cmd.done is True
        assert async_cmd.exit_code not in (None, 0)
        assert target.exists() is False

    asyncio.run(run())


def test_sendmessage_search_hint_uses_queue_naming(tmp_path):
    registry = ToolRegistry()
    AgentService(
        tool_registry=registry,
        workspace_root=Path(tmp_path),
        model_name="gpt-test",
    )

    entry = registry.get("SendMessage")

    assert entry is not None
    assert "queue" in entry.search_hint
    assert "mailbox" not in entry.search_hint


@pytest.mark.asyncio
async def test_sendmessage_enqueues_real_agent_notification_for_target_thread(tmp_path):
    registry = ToolRegistry()
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    service = AgentService(
        tool_registry=registry,
        workspace_root=Path(tmp_path),
        model_name="gpt-test",
        queue_manager=queue_manager,
    )
    await service._register_active_entry(
        AgentEntry(
            agent_id="agent-1",
            name="worker-1",
            thread_id="thread-worker-1",
            status="running",
        )
    )

    result = await service._handle_send_message(
        target_name="worker-1",
        message="hello from coordinator",
        sender_name="coordinator",
    )

    assert result == "Message sent to worker-1."
    items = queue_manager.drain_all("thread-worker-1")
    assert len(items) == 1
    assert items[0].notification_type == "agent"
    assert items[0].sender_name == "coordinator"
    assert "hello from coordinator" in items[0].content


@pytest.mark.asyncio
async def test_sendmessage_uses_service_local_active_state_when_registry_missing(tmp_path):
    registry = ToolRegistry()
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    service = AgentService(
        tool_registry=registry,
        workspace_root=Path(tmp_path),
        model_name="gpt-test",
        queue_manager=queue_manager,
    )
    await service._register_active_entry(
        AgentEntry(
            agent_id="agent-1",
            name="worker-1",
            thread_id="thread-worker-1",
            status="running",
        )
    )

    result = await service._handle_send_message(
        target_name="worker-1",
        message="hello from coordinator",
        sender_name="coordinator",
    )

    assert result == "Message sent to worker-1."
    items = queue_manager.drain_all("thread-worker-1")
    assert len(items) == 1
    assert items[0].notification_type == "agent"
    assert items[0].sender_name == "coordinator"
    assert "hello from coordinator" in items[0].content


@pytest.mark.asyncio
async def test_sendmessage_reaches_target_next_turn_via_steering_middleware(tmp_path):
    registry = ToolRegistry()
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    service = AgentService(
        tool_registry=registry,
        workspace_root=Path(tmp_path),
        model_name="gpt-test",
        queue_manager=queue_manager,
    )
    await service._register_active_entry(
        AgentEntry(
            agent_id="agent-1",
            name="worker-1",
            thread_id="thread-worker-1",
            status="running",
        )
    )

    await service._handle_send_message(
        target_name="worker-1",
        message="queue payload",
        sender_name="coordinator",
    )

    injected = SteeringMiddleware(queue_manager=queue_manager).before_model(
        state={},
        runtime=None,
        config={"configurable": {"thread_id": "thread-worker-1"}},
    )

    assert injected is not None
    messages = injected["messages"]
    assert len(messages) == 1
    assert "queue payload" in str(messages[0].content)
    assert messages[0].metadata["notification_type"] == "agent"
    assert messages[0].metadata["sender_name"] == "coordinator"


@pytest.mark.asyncio
async def test_sendmessage_rejects_ambiguous_running_agent_names(tmp_path):
    registry = ToolRegistry()
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    service = AgentService(
        tool_registry=registry,
        workspace_root=Path(tmp_path),
        model_name="gpt-test",
        queue_manager=queue_manager,
    )
    await service._register_active_entry(
        AgentEntry(
            agent_id="agent-1",
            name="worker",
            thread_id="thread-worker-1",
            status="running",
        )
    )
    await service._register_active_entry(
        AgentEntry(
            agent_id="agent-2",
            name="worker",
            thread_id="thread-worker-2",
            status="running",
        )
    )

    result = await service._handle_send_message(
        target_name="worker",
        message="hello dup",
        sender_name="coordinator",
    )

    assert "ambiguous" in result
    assert queue_manager.drain_all("thread-worker-1") == []
    assert queue_manager.drain_all("thread-worker-2") == []


@pytest.mark.asyncio
async def test_background_agent_progress_notification_reaches_parent_next_turn(tmp_path, monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    def fake_create_leon_agent(*, model_name, workspace_root, **kwargs):
        return _SlowChildAgent("Inspecting repository", release, started)

    monkeypatch.setattr("core.runtime.agent.create_leon_agent", fake_create_leon_agent)

    registry = ToolRegistry()
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    service = AgentService(
        tool_registry=registry,
        workspace_root=Path(tmp_path),
        model_name="gpt-test",
        queue_manager=queue_manager,
        background_progress_interval_s=0.02,
    )

    set_current_thread_id("parent-thread")
    try:
        raw = await service._handle_agent(
            prompt="do work",
            name="worker-1",
            description="Investigating repository",
            run_in_background=True,
        )
        task_id = _agent_tool_json(raw)["task_id"]
        await asyncio.wait_for(started.wait(), timeout=1)
        await asyncio.sleep(0.05)

        injected = SteeringMiddleware(queue_manager=queue_manager).before_model(
            state={},
            runtime=None,
            config={"configurable": {"thread_id": "parent-thread"}},
        )

        assert injected is not None
        text = str(injected["messages"][0].content)
        assert "<worker-progress>" in text
        assert f"<agent-id>{task_id}</agent-id>" in text
        assert "Inspecting repository" in text
    finally:
        release.set()
        await service.cleanup_background_runs()
        set_current_thread_id("")


@pytest.mark.asyncio
async def test_background_agent_completion_notification_waits_for_followthrough_run(tmp_path, monkeypatch):
    def fake_create_leon_agent(*, model_name, workspace_root, **kwargs):
        return _CompleteChildAgent("Finished indexing")

    monkeypatch.setattr("core.runtime.agent.create_leon_agent", fake_create_leon_agent)

    registry = ToolRegistry()
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    service = AgentService(
        tool_registry=registry,
        workspace_root=Path(tmp_path),
        model_name="gpt-test",
        queue_manager=queue_manager,
        background_progress_interval_s=0.02,
    )

    set_current_thread_id("parent-thread")
    try:
        raw = await service._handle_agent(
            prompt="do work",
            name="worker-1",
            description="Index repository",
            run_in_background=True,
        )
        task_id = _agent_tool_json(raw)["task_id"]
        running = _require_running_task(service._tasks[task_id])
        await asyncio.wait_for(running.task, timeout=1)

        injected = SteeringMiddleware(queue_manager=queue_manager).before_model(
            state={},
            runtime=None,
            config={"configurable": {"thread_id": "parent-thread"}},
        )

        assert injected is None
        queued = queue_manager.list_queue("parent-thread")
        assert len(queued) == 1
        text = queued[0]["content"]
        assert "<task-notification>" in text
        assert f"<run-id>{task_id}</run-id>" in text
        assert "<status>completed</status>" in text
        assert "Finished indexing" in text
    finally:
        set_current_thread_id("")


@pytest.mark.asyncio
async def test_mixed_success_and_init_failure_background_agents_queue_both_terminal_notifications(tmp_path, monkeypatch):
    created = 0

    def fake_create_leon_agent(*, model_name, workspace_root, **kwargs):
        nonlocal created
        created += 1
        if created == 1:
            return _CompleteChildAgent("GOOD:BASE:2")
        return _FailingInitChildAgent(RuntimeError("bad child init"))

    monkeypatch.setattr("core.runtime.agent.create_leon_agent", fake_create_leon_agent)

    registry = ToolRegistry()
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    service = AgentService(
        tool_registry=registry,
        workspace_root=Path(tmp_path),
        model_name="gpt-test",
        queue_manager=queue_manager,
    )

    set_current_thread_id("parent-thread")
    try:
        raw_good = await service._handle_agent(
            prompt="good child",
            name="good-child",
            description="good child",
            run_in_background=True,
        )
        raw_bad = await service._handle_agent(
            prompt="bad child",
            name="bad-child",
            description="bad child",
            run_in_background=True,
        )

        await asyncio.wait_for(_require_running_task(service._tasks[_agent_tool_json(raw_good)["task_id"]]).task, timeout=1)
        with pytest.raises(RuntimeError, match="bad child init"):
            await asyncio.wait_for(_require_running_task(service._tasks[_agent_tool_json(raw_bad)["task_id"]]).task, timeout=1)

        queued = queue_manager.list_queue("parent-thread")

        assert len(queued) == 2
        contents = [item["content"] for item in queued]
        assert any("<status>completed</status>" in content and "GOOD:BASE:2" in content for content in contents)
        assert any("<status>error</status>" in content and "Agent failed" in content for content in contents)
    finally:
        set_current_thread_id("")


def test_terminal_background_notification_waits_for_followup_run_during_owner_turn(tmp_path):
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    queue_manager.enqueue(
        "<system-reminder><task-notification><status>error</status><result>Agent failed</result></task-notification></system-reminder>",
        "parent-thread",
        notification_type="agent",
        source="system",
    )

    runtime = type("_Runtime", (), {"current_run_source": "owner"})()
    injected = SteeringMiddleware(queue_manager=queue_manager, agent_runtime=runtime).before_model(
        state={},
        runtime=None,
        config={"configurable": {"thread_id": "parent-thread"}},
    )

    assert injected is None
    queued = queue_manager.list_queue("parent-thread")
    assert len(queued) == 1
    assert "<task-notification>" in queued[0]["content"]


def test_terminal_background_notification_waits_for_followup_run_during_system_turn(tmp_path):
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    queue_manager.enqueue(
        "<system-reminder><task-notification><status>completed</status><result>BG1:STEP1:2</result></task-notification></system-reminder>",
        "parent-thread",
        notification_type="agent",
        source="system",
    )

    runtime = type("_Runtime", (), {"current_run_source": "system"})()
    injected = SteeringMiddleware(queue_manager=queue_manager, agent_runtime=runtime).before_model(
        state={},
        runtime=None,
        config={"configurable": {"thread_id": "parent-thread"}},
    )

    assert injected is None
    queued = queue_manager.list_queue("parent-thread")
    assert len(queued) == 1
    assert "<task-notification>" in queued[0]["content"]


def test_steer_injection_emits_phase_boundary_events(tmp_path):
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    queue_manager.enqueue(
        "Stop the current plan and summarize status.",
        "parent-thread",
        notification_type="steer",
        source="owner",
        is_steer=True,
    )

    class _Runtime:
        def __init__(self) -> None:
            self.events: list[dict[str, str]] = []

        def emit_activity_event(self, event: dict[str, str]) -> None:
            self.events.append(event)

    runtime = _Runtime()
    injected = SteeringMiddleware(queue_manager=queue_manager, agent_runtime=runtime).before_model(
        state={},
        runtime=None,
        config={"configurable": {"thread_id": "parent-thread"}},
    )

    assert injected is not None
    assert str(injected["messages"][0].content) == "Stop the current plan and summarize status."
    assert [event["event"] for event in runtime.events] == ["run_done", "run_start"]
