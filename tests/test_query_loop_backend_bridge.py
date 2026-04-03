"""Backend-facing regression tests for QueryLoop caller-contract bridge."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.web.routers.threads import get_thread_history, get_thread_messages
from backend.web.services.display_builder import DisplayBuilder
from backend.web.services.event_buffer import ThreadEventBuffer
from core.runtime.middleware.queue.manager import MessageQueueManager
from backend.web.services.streaming_service import _repair_incomplete_tool_calls, _run_agent_to_buffer
from core.runtime.middleware.monitor.state_monitor import AgentState
from core.runtime.loop import QueryLoop
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from core.runtime.state import AppState, BootstrapConfig
from core.tools.tool_search.service import ToolSearchService


class _MemoryCheckpointer:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    async def aget(self, cfg):
        return self.store.get(cfg["configurable"]["thread_id"])

    async def aput(self, cfg, checkpoint, metadata, new_versions):
        self.store[cfg["configurable"]["thread_id"]] = checkpoint


class _NoToolModel:
    def __init__(self, text: str = "done") -> None:
        self._text = text

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return AIMessage(content=self._text)


class _ToolSearchInlineSelectModel:
    def __init__(self) -> None:
        self._turn = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if self._turn == 0:
            self._turn += 1
            return AIMessage(
                content="",
                tool_calls=[{"name": "tool_search", "args": {"query": "select:Read,TaskCreate"}, "id": "tc-search"}],
            )
        return AIMessage(content="after-inline-select")


class _FakeDisplayBuilder:
    def __init__(self, cached_entries):
        self._cached_entries = cached_entries
        self.rebuilt_with: tuple[str, list[dict]] | None = None

    def get_entries(self, thread_id: str):
        return self._cached_entries

    def build_from_checkpoint(self, thread_id: str, messages: list[dict]):
        self.rebuilt_with = (thread_id, messages)
        return [{"id": "rebuilt-notice", "role": "notice", "content": "rebuilt"}]

    def get_display_seq(self, thread_id: str) -> int:
        return 7


class _StreamingGraphAgent:
    checkpointer = None

    async def aget_state(self, _config):
        return SimpleNamespace(values={"messages": []})

    async def astream(self, *_args, **_kwargs):
        if False:
            yield None


class _NoResumeGraphAgent(_StreamingGraphAgent):
    def __init__(self) -> None:
        self.astream_calls = 0
        self.aupdate_calls = 0

    async def aupdate_state(self, *_args, **_kwargs):
        self.aupdate_calls += 1

    async def astream(self, *_args, **_kwargs):
        self.astream_calls += 1
        if False:
            yield None
        return


class _StreamingRuntime:
    current_state = AgentState.IDLE

    def __init__(self) -> None:
        self.current_run_source = None
        self._event_callback = None

    def set_event_callback(self, cb) -> None:
        self._event_callback = cb

    def get_status_dict(self) -> dict[str, object]:
        return {"state": {"state": "idle", "flags": {}}}

    def transition(self, new_state) -> bool:
        self.current_state = new_state
        return True


def _make_loop(
    *,
    text: str = "done",
    model=None,
    registry: ToolRegistry | None = None,
    checkpointer: _MemoryCheckpointer | None = None,
) -> QueryLoop:
    return QueryLoop(
        model=model or _NoToolModel(text=text),
        system_prompt=SystemMessage(content="sys"),
        middleware=[],
        checkpointer=checkpointer,
        registry=registry or ToolRegistry(),
        app_state=AppState(),
        runtime=None,
        bootstrap=BootstrapConfig(workspace_root=Path("/tmp"), model_name="test-model"),
        max_turns=5,
    )


@pytest.mark.asyncio
async def test_repair_incomplete_tool_calls_uses_query_loop_state_bridge():
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(checkpointer=checkpointer)
    broken_ai = AIMessage(
        content="",
        tool_calls=[{"name": "Read", "args": {"file_path": "/tmp/a.txt"}, "id": "tc-1"}],
    )
    trailing = HumanMessage(content="after tool")
    trailing.id = "human-after"
    checkpointer.store["repair-live-thread"] = {
        "channel_values": {"messages": [broken_ai, trailing]}
    }

    await _repair_incomplete_tool_calls(
        SimpleNamespace(agent=loop),
        {"configurable": {"thread_id": "repair-live-thread"}},
    )

    state = await loop.aget_state({"configurable": {"thread_id": "repair-live-thread"}})

    assert [msg.__class__.__name__ for msg in state.values["messages"]] == [
        "AIMessage",
        "ToolMessage",
        "HumanMessage",
    ]
    assert [getattr(msg, "content", None) for msg in state.values["messages"]] == [
        "",
        "Error: task was interrupted (server restart or timeout). Results unavailable.",
        "after tool",
    ]


@pytest.mark.asyncio
async def test_get_thread_history_reads_messages_via_query_loop_state_bridge():
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(text="history reply", checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "history-thread"}}

    async for _ in loop.query(
        {"messages": [{"role": "user", "content": "hello"}]},
        config=config,
    ):
        pass

    fake_agent = SimpleNamespace(agent=loop)
    fake_app = SimpleNamespace(state=SimpleNamespace())
    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
    ):
        history = await get_thread_history(
            "history-thread",
            limit=20,
            truncate=300,
            user_id="u",
            app=fake_app,
        )

    assert history["total"] == 2
    assert history["thread_id"] == "history-thread"
    assert [item["role"] for item in history["messages"]] == ["human", "assistant"]
    assert history["messages"][1]["text"] == "history reply"


@pytest.mark.asyncio
async def test_get_thread_history_skips_empty_ai_messages_after_notifications():
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(checkpointer=checkpointer)
    system_notice = HumanMessage(
        content="<system-reminder><task-notification><status>error</status><result>Agent failed</result></task-notification></system-reminder>"
    )
    system_notice.metadata = {"source": "system"}
    checkpointer.store["history-empty-ai-thread"] = {
        "channel_values": {
            "messages": [
                HumanMessage(content="launch background task"),
                system_notice,
                AIMessage(content=""),
            ]
        }
    }

    fake_agent = SimpleNamespace(agent=loop)
    fake_app = SimpleNamespace(state=SimpleNamespace())
    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
    ):
        history = await get_thread_history(
            "history-empty-ai-thread",
            limit=20,
            truncate=300,
            user_id="u",
            app=fake_app,
        )

    assert [item["role"] for item in history["messages"]] == ["human", "notification"]
    assert history["messages"][-1]["text"].startswith("<system-reminder><task-notification>")


@pytest.mark.asyncio
async def test_get_thread_history_retains_tool_search_inline_select_error():
    checkpointer = _MemoryCheckpointer()
    registry = ToolRegistry()
    registry.register(
        ToolEntry(
            name="Read",
            mode=ToolMode.INLINE,
            schema={"name": "Read", "description": "read file"},
            handler=lambda **_: "read",
            source="test",
        )
    )
    registry.register(
        ToolEntry(
            name="TaskCreate",
            mode=ToolMode.DEFERRED,
            schema={"name": "TaskCreate", "description": "create task"},
            handler=lambda **_: "task",
            source="test",
        )
    )
    ToolSearchService(registry)
    loop = _make_loop(
        model=_ToolSearchInlineSelectModel(),
        registry=registry,
        checkpointer=checkpointer,
    )
    config = {"configurable": {"thread_id": "history-tool-search-inline-select"}}

    async for _ in loop.query(
        {"messages": [{"role": "user", "content": "probe inline select"}]},
        config=config,
    ):
        pass

    fake_agent = SimpleNamespace(agent=loop)
    fake_app = SimpleNamespace(state=SimpleNamespace())
    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
    ):
        history = await get_thread_history(
            "history-tool-search-inline-select",
            limit=20,
            truncate=300,
            user_id="u",
            app=fake_app,
        )

    assert [item["role"] for item in history["messages"]] == ["human", "tool_call", "tool_result", "assistant"]
    assert history["messages"][1]["tool"] == "tool_search"
    assert "<tool_use_error>" in history["messages"][2]["text"]
    assert "inline/already-available tools: Read" in history["messages"][2]["text"]
    assert history["messages"][3]["text"] == "after-inline-select"


@pytest.mark.asyncio
async def test_query_loop_does_not_persist_terminal_empty_ai_after_system_notification_resume():
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(text="", checkpointer=checkpointer)
    system_notice = HumanMessage(
        content="<system-reminder><task-notification><status>error</status><result>Agent failed</result></task-notification></system-reminder>"
    )
    system_notice.metadata = {"source": "system", "notification_type": "agent"}
    checkpointer.store["resume-empty-ai-thread"] = {
        "channel_values": {
            "messages": [
                HumanMessage(content="launch background task"),
                system_notice,
            ]
        }
    }

    async for _ in loop.query(
        None,
        config={"configurable": {"thread_id": "resume-empty-ai-thread"}},
    ):
        pass

    state = await loop.aget_state({"configurable": {"thread_id": "resume-empty-ai-thread"}})

    assert [msg.__class__.__name__ for msg in state.values["messages"]] == [
        "HumanMessage",
        "HumanMessage",
    ]
    assert state.values["messages"][-1].content.startswith("<system-reminder><task-notification>")


@pytest.mark.asyncio
async def test_get_thread_messages_rebuilds_idle_thread_when_cached_entries_are_stale():
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(text="history reply", checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "detail-thread"}}

    async for _ in loop.query(
        {"messages": [{"role": "user", "content": "hello"}]},
        config=config,
    ):
        pass

    display_builder = _FakeDisplayBuilder(cached_entries=[{"id": "stale-turn", "role": "assistant", "segments": []}])
    fake_agent = SimpleNamespace(
        agent=loop,
        runtime=SimpleNamespace(current_state=AgentState.IDLE),
    )
    fake_app = SimpleNamespace(state=SimpleNamespace(display_builder=display_builder))

    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
        patch("backend.web.routers.threads.get_sandbox_info", return_value={"type": "local"}),
    ):
        detail = await get_thread_messages(
            "detail-thread",
            user_id="u",
            app=fake_app,
        )

    assert detail["entries"] == [{"id": "rebuilt-notice", "role": "notice", "content": "rebuilt"}]
    assert display_builder.rebuilt_with is not None
    rebuilt_thread_id, rebuilt_messages = display_builder.rebuilt_with
    assert rebuilt_thread_id == "detail-thread"
    assert [msg["type"] for msg in rebuilt_messages] == ["HumanMessage", "AIMessage"]


@pytest.mark.asyncio
async def test_run_agent_to_buffer_emits_notice_for_system_agent_notifications(monkeypatch, tmp_path):
    seq = 0

    async def fake_append_event(thread_id, run_id, event, message_id=None, run_event_repo=None):
        nonlocal seq
        seq += 1
        return seq

    async def fake_cleanup_old_runs(thread_id, keep_latest=1, run_event_repo=None):
        return 0

    monkeypatch.setattr("backend.web.services.event_store.append_event", fake_append_event)
    monkeypatch.setattr("backend.web.services.streaming_service.cleanup_old_runs", fake_cleanup_old_runs)
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *args, **kwargs: None)

    agent = SimpleNamespace(
        agent=_StreamingGraphAgent(),
        runtime=_StreamingRuntime(),
        storage_container=None,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            display_builder=DisplayBuilder(),
            thread_tasks={},
            thread_event_buffers={},
            subagent_buffers={},
            queue_manager=MessageQueueManager(db_path=str(tmp_path / "queue.db")),
            thread_last_active={},
            typing_tracker=None,
        )
    )
    thread_buf = ThreadEventBuffer()

    await _run_agent_to_buffer(
        agent,
        "thread-notice",
        "<system-reminder><task-notification><status>completed</status></task-notification></system-reminder>",
        app,
        False,
        thread_buf,
        "run-notice",
        message_metadata={"source": "system", "notification_type": "agent"},
    )

    entries = app.state.display_builder.get_entries("thread-notice")
    assert entries is not None
    assert entries[0]["segments"] == [
        {
            "type": "notice",
            "content": "<system-reminder><task-notification><status>completed</status></task-notification></system-reminder>",
            "notification_type": "agent",
        }
    ]


@pytest.mark.asyncio
async def test_run_agent_to_buffer_persists_terminal_notifications_for_history(monkeypatch, tmp_path):
    seq = 0

    async def fake_append_event(thread_id, run_id, event, message_id=None, run_event_repo=None):
        nonlocal seq
        seq += 1
        return seq

    async def fake_cleanup_old_runs(thread_id, keep_latest=1, run_event_repo=None):
        return 0

    monkeypatch.setattr("backend.web.services.event_store.append_event", fake_append_event)
    monkeypatch.setattr("backend.web.services.streaming_service.cleanup_old_runs", fake_cleanup_old_runs)
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *args, **kwargs: None)

    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(checkpointer=checkpointer)
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    queue_manager.enqueue(
        "<system-reminder><task-notification><status>error</status><result>Agent failed</result></task-notification></system-reminder>",
        "thread-terminal-history",
        notification_type="agent",
        source="system",
    )

    agent = SimpleNamespace(
        agent=loop,
        runtime=_StreamingRuntime(),
        storage_container=None,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            display_builder=DisplayBuilder(),
            thread_tasks={},
            thread_event_buffers={},
            subagent_buffers={},
            queue_manager=queue_manager,
            thread_last_active={},
            typing_tracker=None,
        )
    )
    thread_buf = ThreadEventBuffer()

    await _run_agent_to_buffer(
        agent,
        "thread-terminal-history",
        "<system-reminder><task-notification><status>completed</status><result>BG_OK</result></task-notification></system-reminder>",
        app,
        False,
        thread_buf,
        "run-terminal-history",
        message_metadata={"source": "system", "notification_type": "agent"},
    )

    state = await loop.aget_state({"configurable": {"thread_id": "thread-terminal-history"}})

    assert [msg.__class__.__name__ for msg in state.values["messages"]] == [
        "HumanMessage",
        "HumanMessage",
    ]
    assert "BG_OK" in state.values["messages"][0].content
    assert "Agent failed" in state.values["messages"][1].content


@pytest.mark.asyncio
async def test_run_agent_to_buffer_skips_graph_resume_for_terminal_background_notifications(monkeypatch, tmp_path):
    seq = 0

    async def fake_append_event(thread_id, run_id, event, message_id=None, run_event_repo=None):
        nonlocal seq
        seq += 1
        return seq

    async def fake_cleanup_old_runs(thread_id, keep_latest=1, run_event_repo=None):
        return 0

    monkeypatch.setattr("backend.web.services.event_store.append_event", fake_append_event)
    monkeypatch.setattr("backend.web.services.streaming_service.cleanup_old_runs", fake_cleanup_old_runs)
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *args, **kwargs: None)

    graph = _NoResumeGraphAgent()
    agent = SimpleNamespace(
        agent=graph,
        runtime=_StreamingRuntime(),
        storage_container=None,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            display_builder=DisplayBuilder(),
            thread_tasks={},
            thread_event_buffers={},
            subagent_buffers={},
            queue_manager=MessageQueueManager(db_path=str(tmp_path / "queue.db")),
            thread_last_active={},
            typing_tracker=None,
        )
    )
    thread_buf = ThreadEventBuffer()

    await _run_agent_to_buffer(
        agent,
        "thread-terminal-notice",
        "<system-reminder><task-notification><status>completed</status><result>BG_SEEN:RESULT:3</result></task-notification></system-reminder>",
        app,
        False,
        thread_buf,
        "run-terminal-notice",
        message_metadata={"source": "system", "notification_type": "agent"},
    )

    assert graph.astream_calls == 0
    assert graph.aupdate_calls == 1


@pytest.mark.asyncio
async def test_run_agent_to_buffer_batches_additional_terminal_notifications(monkeypatch, tmp_path):
    seq = 0

    async def fake_append_event(thread_id, run_id, event, message_id=None, run_event_repo=None):
        nonlocal seq
        seq += 1
        return seq

    async def fake_cleanup_old_runs(thread_id, keep_latest=1, run_event_repo=None):
        return 0

    monkeypatch.setattr("backend.web.services.event_store.append_event", fake_append_event)
    monkeypatch.setattr("backend.web.services.streaming_service.cleanup_old_runs", fake_cleanup_old_runs)
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *args, **kwargs: None)

    start_calls: list[tuple[str, str, dict | None]] = []

    def fake_start_agent_run(agent, thread_id, message, app, enable_trajectory=False, message_metadata=None):
        start_calls.append((thread_id, message, message_metadata))
        return "run-next"

    monkeypatch.setattr("backend.web.services.streaming_service.start_agent_run", fake_start_agent_run)

    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    queue_manager.enqueue(
        "<system-reminder><task-notification><status>error</status><result>Agent failed</result></task-notification></system-reminder>",
        "thread-batch-notice",
        notification_type="agent",
    )
    queue_manager.enqueue(
        "<system-reminder><CommandNotification><Status>completed</Status><Output>42</Output></CommandNotification></system-reminder>",
        "thread-batch-notice",
        notification_type="command",
    )

    agent = SimpleNamespace(
        agent=_StreamingGraphAgent(),
        runtime=_StreamingRuntime(),
        storage_container=None,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            display_builder=DisplayBuilder(),
            thread_tasks={},
            thread_event_buffers={},
            subagent_buffers={},
            queue_manager=queue_manager,
            thread_last_active={},
            typing_tracker=None,
        )
    )
    thread_buf = ThreadEventBuffer()

    await _run_agent_to_buffer(
        agent,
        "thread-batch-notice",
        "<system-reminder><task-notification><status>completed</status><result>BG_OK</result></task-notification></system-reminder>",
        app,
        False,
        thread_buf,
        "run-batch-notice",
        message_metadata={"source": "system", "notification_type": "agent"},
    )

    entries = app.state.display_builder.get_entries("thread-batch-notice")
    assert entries is not None
    notice_segments = [segment for segment in entries[0]["segments"] if segment.get("type") == "notice"]
    assert len(notice_segments) == 3
    assert "BG_OK" in notice_segments[0]["content"]
    assert "Agent failed" in notice_segments[1]["content"]
    assert "CommandNotification" in notice_segments[2]["content"]
    assert start_calls == []
    assert queue_manager.list_queue("thread-batch-notice") == []
