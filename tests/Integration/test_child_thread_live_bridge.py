from __future__ import annotations

import asyncio
from types import SimpleNamespace

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
            "tokens": 0,
            "cost": 0.0,
            "calls": 0,
            "ctx_percent": 0.0,
        }

    def get_status_dict(self) -> dict:
        return {
            "state": {"state": self.current_state.value, "flags": {}},
            "tokens": {},
            "context": {},
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


def test_live_tool_result_restores_subagent_stream_from_agent_background_json():
    builder = DisplayBuilder()
    thread_id = "parent-thread"

    builder.apply_event(
        thread_id,
        "run_start",
        {"run_id": "run-1", "source": "owner", "showing": True},
    )
    builder.apply_event(
        thread_id,
        "tool_call",
        {
            "id": "tc-agent-1",
            "name": "Agent",
            "args": {"prompt": "do work", "run_in_background": True},
            "showing": True,
        },
    )

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


def test_task_start_can_patch_background_agent_after_tool_result_race():
    builder = DisplayBuilder()
    thread_id = "parent-thread"

    builder.apply_event(
        thread_id,
        "run_start",
        {"run_id": "run-1", "source": "owner", "showing": True},
    )
    builder.apply_event(
        thread_id,
        "tool_call",
        {
            "id": "tc-agent-race",
            "name": "Agent",
            "args": {"prompt": "do work", "run_in_background": True},
            "showing": True,
        },
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
