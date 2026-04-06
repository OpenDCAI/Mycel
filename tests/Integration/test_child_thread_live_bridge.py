from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.web.routers import threads as threads_router
from backend.web.services.display_builder import DisplayBuilder
from backend.web.services.event_buffer import ThreadEventBuffer
from backend.web.services.streaming_service import run_child_thread_live
from backend.web.utils.serializers import serialize_message
from core.runtime.middleware.monitor import AgentState
from core.runtime.middleware.queue.manager import MessageQueueManager


class _FakeRuntime:
    def __init__(self) -> None:
        self.current_state = AgentState.IDLE
        self._event_callback = None
        self._activity_sink = None
        self.state = SimpleNamespace(flags=SimpleNamespace(is_compacting=False))
        self.calls = 0
        self.tokens = 0
        self.cost = 0.0
        self.ctx_percent = 0.0

    def transition(self, new_state: AgentState) -> bool:
        self.current_state = new_state
        return True

    def set_event_callback(self, callback) -> None:
        self._event_callback = callback

    def bind_thread(self, activity_sink) -> None:
        self._activity_sink = activity_sink

    def unbind_thread(self) -> None:
        self._activity_sink = None

    def get_compact_dict(self) -> dict:
        return {
            "state": self.current_state.value,
            "tokens": self.tokens,
            "cost": self.cost,
            "calls": self.calls,
            "ctx_percent": self.ctx_percent,
        }

    def get_status_dict(self) -> dict:
        return {
            "state": {"state": self.current_state.value, "flags": {}},
            "tokens": {"total": self.tokens},
            "context": {"percent": self.ctx_percent},
            "calls": self.calls,
            "cost": self.cost,
        }


class _BlockingChildGraph:
    def __init__(self) -> None:
        self.messages: list = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.system_prompt = None

    async def aget_state(self, _config):
        return SimpleNamespace(values={"messages": list(self.messages)})

    async def aupdate_state(self, _config, input_data, as_node=None):
        self.messages.extend(input_data.get("messages", []))

    async def astream(self, input_data, config=None, stream_mode=None):
        if input_data is not None:
            self.messages.extend(input_data.get("messages", []))
        self.started.set()
        await self.release.wait()
        yield ("messages", (SimpleNamespace(__class__=SimpleNamespace(__name__="AIMessageChunk")), {}))
        ai = AIMessage(content="CHILD_DONE")
        ai.id = "ai-child-1"
        self.messages.append(ai)
        yield ("updates", {"agent": {"messages": [ai]}})


class _BlockingChildAgent:
    def __init__(self) -> None:
        self.runtime = _FakeRuntime()
        self.agent = _BlockingChildGraph()


def _prime_agent_turn(
    builder: DisplayBuilder,
    thread_id: str,
    *,
    tool_call_id: str = "tc-agent-1",
    args: dict | None = None,
    run_id: str = "run-1",
) -> None:
    builder.apply_event(
        thread_id,
        "run_start",
        {"run_id": run_id, "source": "owner", "showing": True},
    )
    builder.apply_event(
        thread_id,
        "tool_call",
        {
            "id": tool_call_id,
            "name": "Agent",
            "args": args or {"prompt": "do work"},
            "showing": True,
        },
    )


def _set_single_subagent_entry(
    builder: DisplayBuilder,
    thread_id: str,
    *,
    task_id: str,
    thread_ref: str,
    status: str,
    result: str,
    description: str = "inspect workspace",
) -> None:
    builder.set_entries(
        thread_id,
        [
            {"id": "u1", "role": "user", "content": "do work", "timestamp": 1},
            {
                "id": "a1",
                "role": "assistant",
                "timestamp": 2,
                "segments": [
                    {
                        "type": "tool",
                        "step": {
                            "id": "call-agent-1",
                            "name": "Agent",
                            "args": {"description": description},
                            "status": "done",
                            "result": result,
                            "subagent_stream": {
                                "task_id": task_id,
                                "thread_id": thread_ref,
                                "description": description,
                                "text": "",
                                "tool_calls": [],
                                "status": status,
                            },
                        },
                    }
                ],
            },
        ],
    )


def _make_router_app(
    builder: DisplayBuilder,
    thread_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> SimpleNamespace:
    fake_agent = SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.ACTIVE), agent=SimpleNamespace(aget_state=None))
    monkeypatch.setattr(threads_router, "get_or_create_agent", AsyncMock(return_value=fake_agent))
    return SimpleNamespace(
        state=SimpleNamespace(
            display_builder=builder,
            agent_pool={},
            thread_sandbox={thread_id: "local"},
        )
    )


@pytest.mark.asyncio
async def test_run_child_thread_live_rebinds_from_parent_sink_and_surfaces_runtime_and_detail_before_completion():
    child_thread_id = "subagent-live-1"
    agent = _BlockingChildAgent()
    parent_events: list[dict] = []

    async def _parent_sink(event: dict) -> None:
        parent_events.append(event)

    agent.runtime.bind_thread(_parent_sink)
    app = SimpleNamespace(
        state=SimpleNamespace(
            display_builder=DisplayBuilder(),
            queue_manager=MessageQueueManager(),
            _event_loop=asyncio.get_running_loop(),
            thread_event_buffers={},
            thread_tasks={},
            thread_last_active={},
            agent_pool={},
            thread_sandbox={child_thread_id: "local"},
            thread_cwd={},
            thread_repo=SimpleNamespace(get_by_id=lambda thread_id: {"model": "gpt-live"} if thread_id == child_thread_id else None),
        )
    )

    task = asyncio.create_task(
        run_child_thread_live(
            agent,
            child_thread_id,
            "child prompt",
            app,
            input_messages=[HumanMessage(content="child prompt")],
        )
    )

    await agent.agent.started.wait()

    runtime = await threads_router.get_thread_runtime(child_thread_id, stream=False, user_id="owner-1", app=app)
    detail = await threads_router.get_thread_messages(child_thread_id, user_id="owner-1", app=app)

    assert runtime["state"]["state"] == "active"
    assert detail["entries"]
    assert detail["entries"][0]["role"] == "user"
    assert detail["entries"][0]["content"] == "child prompt"
    assert isinstance(app.state.thread_event_buffers[child_thread_id], ThreadEventBuffer)
    assert app.state.agent_pool[f"{child_thread_id}:local"] is agent
    assert agent.runtime._activity_sink is not _parent_sink
    assert parent_events == []

    agent.agent.release.set()
    result = await task

    assert result == "CHILD_DONE"


@pytest.mark.asyncio
async def test_run_child_thread_live_raises_when_child_run_emits_error_event(monkeypatch):
    child_thread_id = "subagent-live-error"
    agent = _BlockingChildAgent()
    app = SimpleNamespace(
        state=SimpleNamespace(
            display_builder=DisplayBuilder(),
            queue_manager=MessageQueueManager(),
            _event_loop=asyncio.get_running_loop(),
            thread_event_buffers={},
            thread_tasks={},
            thread_last_active={},
            agent_pool={},
            thread_sandbox={child_thread_id: "local"},
            thread_cwd={},
            thread_repo=SimpleNamespace(get_by_id=lambda thread_id: {"model": "gpt-live"} if thread_id == child_thread_id else None),
        )
    )

    def fake_start_agent_run(agent, thread_id, message, app, enable_trajectory=False, message_metadata=None, input_messages=None):
        async def _fake_run():
            thread_buf = app.state.thread_event_buffers[thread_id]
            await thread_buf.put({"event": "error", "data": json.dumps({"error": "child model init failed"})})
            return ""

        app.state.thread_tasks[thread_id] = asyncio.create_task(_fake_run())
        return "run-error-1"

    monkeypatch.setattr("backend.web.services.streaming_service.start_agent_run", fake_start_agent_run)

    with pytest.raises(RuntimeError, match="child model init failed"):
        await run_child_thread_live(
            agent,
            child_thread_id,
            "child prompt",
            app,
            input_messages=[HumanMessage(content="child prompt")],
        )


@pytest.mark.asyncio
async def test_run_child_thread_live_raises_when_child_never_makes_a_model_call(monkeypatch):
    child_thread_id = "subagent-live-no-call"
    agent = _BlockingChildAgent()
    app = SimpleNamespace(
        state=SimpleNamespace(
            display_builder=DisplayBuilder(),
            queue_manager=MessageQueueManager(),
            _event_loop=asyncio.get_running_loop(),
            thread_event_buffers={},
            thread_tasks={},
            thread_last_active={},
            agent_pool={},
            thread_sandbox={child_thread_id: "local"},
            thread_cwd={},
            thread_repo=SimpleNamespace(get_by_id=lambda thread_id: {"model": "gpt-live"} if thread_id == child_thread_id else None),
        )
    )

    def fake_start_agent_run(agent, thread_id, message, app, enable_trajectory=False, message_metadata=None, input_messages=None):
        async def _fake_run():
            return ""

        app.state.thread_tasks[thread_id] = asyncio.create_task(_fake_run())
        return "run-no-call-1"

    monkeypatch.setattr("backend.web.services.streaming_service.start_agent_run", fake_start_agent_run)

    with pytest.raises(RuntimeError, match="before first model call"):
        await run_child_thread_live(
            agent,
            child_thread_id,
            "child prompt",
            app,
            input_messages=[HumanMessage(content="child prompt")],
        )


def test_live_tool_result_restores_subagent_stream_from_agent_background_json():
    builder = DisplayBuilder()
    thread_id = "parent-thread"
    _prime_agent_turn(builder, thread_id, args={"prompt": "do work", "run_in_background": True})

    delta = builder.apply_event(
        thread_id,
        "tool_result",
        {
            "tool_call_id": "tc-agent-1",
            "name": "Agent",
            "content": (
                '{"task_id":"task-123","agent_name":"agent-task-123",'
                '"thread_id":"subagent-task-123","status":"running",'
                '"message":"Agent started in background. Use TaskOutput to get result."}'
            ),
            "metadata": {},
            "showing": True,
        },
    )

    seg = builder.get_entries(thread_id)[0]["segments"][0]
    assert delta is not None
    assert seg["step"]["subagent_stream"]["task_id"] == "task-123"
    assert seg["step"]["subagent_stream"]["thread_id"] == "subagent-task-123"
    assert seg["step"]["subagent_stream"]["status"] == "running"


def test_live_tool_result_restores_subagent_stream_from_blocking_agent_metadata():
    builder = DisplayBuilder()
    thread_id = "parent-thread"
    _prime_agent_turn(builder, thread_id)

    delta = builder.apply_event(
        thread_id,
        "tool_result",
        {
            "tool_call_id": "tc-agent-1",
            "name": "Agent",
            "content": "CHILD_DONE",
            "metadata": {
                "task_id": "task-456",
                "subagent_thread_id": "subagent-task-456",
                "description": "blocking child",
            },
            "showing": True,
        },
    )

    seg = builder.get_entries(thread_id)[0]["segments"][0]
    assert delta is not None
    assert seg["step"]["subagent_stream"]["task_id"] == "task-456"
    assert seg["step"]["subagent_stream"]["thread_id"] == "subagent-task-456"
    assert seg["step"]["subagent_stream"]["status"] == "completed"


def test_live_hidden_user_message_does_not_append_entry():
    builder = DisplayBuilder()
    thread_id = "hidden-user-thread"

    delta = builder.apply_event(
        thread_id,
        "user_message",
        {
            "content": "<ask_user_question_answers>{}</ask_user_question_answers>",
            "showing": False,
        },
    )

    assert delta is None
    assert builder.get_entries(thread_id) == []


def test_live_hidden_ask_user_answer_message_appends_hidden_anchor_entry():
    builder = DisplayBuilder()
    thread_id = "hidden-ask-answer-thread"

    delta = builder.apply_event(
        thread_id,
        "user_message",
        {
            "content": "",
            "showing": False,
            "ask_user_question_answered": {
                "questions": [
                    {
                        "header": "Choice",
                        "question": "Pick one",
                        "options": [{"label": "Alpha", "description": "A"}],
                    }
                ],
                "answers": [
                    {
                        "header": "Choice",
                        "question": "Pick one",
                        "selected_options": ["Alpha"],
                    }
                ],
            },
        },
    )

    assert delta is not None
    assert delta["type"] == "append_entry"
    entry = builder.get_entries(thread_id)[0]
    assert entry["role"] == "user"
    assert entry["showing"] is False
    assert entry["ask_user_question_answered"]["answers"][0]["selected_options"] == ["Alpha"]


def test_checkpoint_rebuild_preserves_hidden_ask_user_answer_anchor_entry():
    builder = DisplayBuilder()
    thread_id = "checkpoint-ask-answer-thread"
    rebuilt = builder.build_from_checkpoint(
        thread_id,
        [
            serialize_message(
                HumanMessage(
                    content="ignored",
                    metadata={
                        "source": "internal",
                        "ask_user_question_answered": {
                            "questions": [
                                {
                                    "header": "Choice",
                                    "question": "Pick one",
                                    "options": [{"label": "Alpha", "description": "A"}],
                                }
                            ],
                            "answers": [
                                {
                                    "header": "Choice",
                                    "question": "Pick one",
                                    "selected_options": ["Alpha"],
                                }
                            ],
                        },
                    },
                )
            )
        ],
    )

    assert len(rebuilt) == 1
    assert rebuilt[0]["showing"] is False
    assert rebuilt[0]["ask_user_question_answered"]["answers"][0]["selected_options"] == ["Alpha"]


def test_task_start_can_patch_background_agent_after_tool_result_race():
    builder = DisplayBuilder()
    thread_id = "parent-thread"
    _prime_agent_turn(
        builder,
        thread_id,
        tool_call_id="tc-agent-race",
        args={"prompt": "do work", "run_in_background": True},
    )
    builder.apply_event(
        thread_id,
        "tool_result",
        {
            "tool_call_id": "tc-agent-race",
            "name": "Agent",
            "content": "Agent started in background.",
            "metadata": {},
            "showing": True,
        },
    )

    delta = builder.apply_event(
        thread_id,
        "task_start",
        {
            "task_id": "task-race",
            "thread_id": "subagent-task-race",
            "description": "late task start",
        },
    )

    seg = builder.get_entries(thread_id)[0]["segments"][0]
    assert delta is not None
    assert seg["step"]["status"] == "done"
    assert seg["step"]["subagent_stream"]["task_id"] == "task-race"
    assert seg["step"]["subagent_stream"]["thread_id"] == "subagent-task-race"
    assert seg["step"]["subagent_stream"]["status"] == "running"


@pytest.mark.parametrize("task_status", ["completed", "error", "cancelled"])
def test_live_notice_reconciles_subagent_stream_status_from_terminal_notification(task_status: str):
    builder = DisplayBuilder()
    thread_id = "parent-thread"
    _prime_agent_turn(builder, thread_id, args={"prompt": "do work", "run_in_background": True})
    builder.apply_event(
        thread_id,
        "tool_result",
        {
            "tool_call_id": "tc-agent-1",
            "name": "Agent",
            "content": (
                '{"task_id":"task-123","agent_name":"agent-task-123",'
                '"thread_id":"subagent-task-123","status":"running",'
                '"message":"Agent started in background. Use TaskOutput to get result."}'
            ),
            "metadata": {},
            "showing": True,
        },
    )

    delta = builder.apply_event(
        thread_id,
        "notice",
        {
            "content": (
                "<system-reminder>\n"
                "<task-notification>\n"
                "  <run-id>task-123</run-id>\n"
                f"  <status>{task_status}</status>\n"
                "  <description>child task</description>\n"
                "  <summary>child task</summary>\n"
                "  <result>CHILD_DONE</result>\n"
                "</task-notification>\n"
                "</system-reminder>"
            ),
            "source": "system",
            "notification_type": "agent",
        },
    )

    seg = builder.get_entries(thread_id)[0]["segments"][0]
    assert delta is not None
    assert seg["step"]["subagent_stream"]["task_id"] == "task-123"
    assert seg["step"]["subagent_stream"]["thread_id"] == "subagent-task-123"
    assert seg["step"]["subagent_stream"]["status"] == task_status


def test_checkpoint_rebuild_reconciles_subagent_stream_status_from_terminal_notification():
    builder = DisplayBuilder()
    thread_id = "parent-thread"

    ai = AIMessage(
        content="",
        tool_calls=[{"name": "Agent", "args": {"prompt": "do work", "run_in_background": True}, "id": "tc-agent-1"}],
    )
    tool = ToolMessage(
        content=(
            '{"task_id":"task-123","agent_name":"agent-task-123",'
            '"thread_id":"subagent-task-123","status":"running",'
            '"message":"Agent started in background. Use TaskOutput to get result."}'
        ),
        name="Agent",
        tool_call_id="tc-agent-1",
    )
    notice = HumanMessage(
        content=(
            "<system-reminder>\n"
            "<task-notification>\n"
            "  <run-id>task-123</run-id>\n"
            "  <status>completed</status>\n"
            "  <description>child task</description>\n"
            "  <summary>child task</summary>\n"
            "  <result>CHILD_DONE</result>\n"
            "</task-notification>\n"
            "</system-reminder>"
        )
    )
    notice.metadata = {"source": "system", "notification_type": "agent"}

    entries = builder.build_from_checkpoint(
        thread_id,
        [serialize_message(ai), serialize_message(tool), serialize_message(notice)],
    )

    seg = entries[0]["segments"][0]
    assert seg["step"]["subagent_stream"]["task_id"] == "task-123"
    assert seg["step"]["subagent_stream"]["thread_id"] == "subagent-task-123"
    assert seg["step"]["subagent_stream"]["status"] == "completed"


def test_checkpoint_rebuild_restores_blocking_subagent_stream_from_tool_result_meta():
    builder = DisplayBuilder()
    thread_id = "parent-thread"

    ai = AIMessage(
        content="",
        tool_calls=[{"name": "Agent", "args": {"prompt": "do work"}, "id": "tc-agent-1"}],
    )
    tool = ToolMessage(
        content="CHILD_DONE",
        name="Agent",
        tool_call_id="tc-agent-1",
        additional_kwargs={
            "tool_result_meta": {
                "task_id": "task-456",
                "subagent_thread_id": "subagent-task-456",
                "description": "blocking child",
                "kind": "success",
                "source": "local",
            }
        },
    )

    entries = builder.build_from_checkpoint(
        thread_id,
        [serialize_message(ai), serialize_message(tool)],
    )

    seg = entries[0]["segments"][0]
    assert seg["step"]["subagent_stream"]["task_id"] == "task-456"
    assert seg["step"]["subagent_stream"]["thread_id"] == "subagent-task-456"
    assert seg["step"]["subagent_stream"]["status"] == "completed"


@pytest.mark.asyncio
async def test_list_tasks_includes_subagent_stream_from_display_entries():
    thread_id = "parent-thread-tasks"
    builder = DisplayBuilder()
    _set_single_subagent_entry(
        builder,
        thread_id,
        task_id="task-123",
        thread_ref="subagent-task-123",
        status="completed",
        result="workspace looks empty",
    )
    monkeypatch = pytest.MonkeyPatch()
    app = _make_router_app(builder, thread_id, monkeypatch)

    tasks = await threads_router.list_tasks(thread_id, request=SimpleNamespace(app=app))

    assert tasks == [
        {
            "task_id": "task-123",
            "task_type": "agent",
            "status": "completed",
            "command_line": None,
            "description": "inspect workspace",
            "exit_code": None,
            "error": None,
        }
    ]
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_get_task_returns_subagent_stream_result_from_display_entries():
    thread_id = "parent-thread-task-detail"
    builder = DisplayBuilder()
    _set_single_subagent_entry(
        builder,
        thread_id,
        task_id="task-123",
        thread_ref="subagent-task-123",
        status="completed",
        result="workspace looks empty",
    )
    monkeypatch = pytest.MonkeyPatch()
    app = _make_router_app(builder, thread_id, monkeypatch)

    task = await threads_router.get_task(thread_id, "task-123", request=SimpleNamespace(app=app))

    assert task == {
        "task_id": "task-123",
        "task_type": "agent",
        "status": "completed",
        "command_line": None,
        "result": "workspace looks empty",
        "text": "workspace looks empty",
    }
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_blocking_subagent_done_state_overrides_stale_running_stream_on_detail_and_tasks(monkeypatch):
    thread_id = "parent-thread-stale-running-completed"
    builder = DisplayBuilder()
    _set_single_subagent_entry(
        builder,
        thread_id,
        task_id="task-stale-completed",
        thread_ref="subagent-task-stale-completed",
        status="running",
        result="workspace looks empty",
    )
    app = _make_router_app(builder, thread_id, monkeypatch)

    detail = await threads_router.get_thread_messages(thread_id, user_id="owner-1", app=app)
    tasks = await threads_router.list_tasks(thread_id, request=SimpleNamespace(app=app))
    task = await threads_router.get_task(thread_id, "task-stale-completed", request=SimpleNamespace(app=app))

    stream = detail["entries"][1]["segments"][0]["step"]["subagent_stream"]
    assert stream["status"] == "completed"
    assert tasks[0]["status"] == "completed"
    assert task["status"] == "completed"


@pytest.mark.asyncio
async def test_blocking_subagent_error_overrides_stale_running_stream_on_detail_and_tasks(monkeypatch):
    thread_id = "parent-thread-stale-running-error"
    builder = DisplayBuilder()
    _set_single_subagent_entry(
        builder,
        thread_id,
        task_id="task-stale-error",
        thread_ref="subagent-task-stale-error",
        status="running",
        result="<tool_use_error>Agent failed: bad child model</tool_use_error>",
    )
    app = _make_router_app(builder, thread_id, monkeypatch)

    detail = await threads_router.get_thread_messages(thread_id, user_id="owner-1", app=app)
    tasks = await threads_router.list_tasks(thread_id, request=SimpleNamespace(app=app))
    task = await threads_router.get_task(thread_id, "task-stale-error", request=SimpleNamespace(app=app))

    stream = detail["entries"][1]["segments"][0]["step"]["subagent_stream"]
    assert stream["status"] == "error"
    assert tasks[0]["status"] == "error"
    assert task["status"] == "error"
