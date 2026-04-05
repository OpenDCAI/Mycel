"""Backend-facing regression tests for QueryLoop caller-contract bridge."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from backend.web.models.requests import SendMessageRequest
from backend.web.routers import threads as threads_router
from backend.web.routers.threads import get_thread_history, get_thread_messages
from backend.web.services.display_builder import DisplayBuilder
from backend.web.services.event_buffer import ThreadEventBuffer
from backend.web.services.streaming_service import (
    _ensure_thread_handlers,
    _repair_incomplete_tool_calls,
    _run_agent_to_buffer,
    start_agent_run,
)
from core.runtime.loop import QueryLoop
from core.runtime.middleware.memory.middleware import MemoryMiddleware
from core.runtime.middleware.monitor.state_monitor import AgentState
from core.runtime.middleware.queue.manager import MessageQueueManager
from core.runtime.middleware.queue.middleware import SteeringMiddleware
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from core.runtime.state import AppState, BootstrapConfig
from core.tools.tool_search.service import ToolSearchService


class _MemoryCheckpointer:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    async def aget(self, cfg):
        return self.store.get(cfg["configurable"]["thread_id"])

    async def aget_tuple(self, cfg):
        return None

    async def aput(self, cfg, checkpoint, metadata, new_versions):
        self.store[cfg["configurable"]["thread_id"]] = checkpoint


class _NoToolModel:
    def __init__(self, text: str = "done") -> None:
        self._text = text

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return AIMessage(content=self._text)


class _TurnTextModel:
    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)
        self._index = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if self._index < len(self._texts):
            text = self._texts[self._index]
            self._index += 1
            return AIMessage(content=text)
        return AIMessage(content=self._texts[-1] if self._texts else "done")


class _TerminalFollowthroughPromptAwareModel:
    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        system_text = ""
        if messages and messages[0].__class__.__name__ == "SystemMessage":
            system_text = getattr(messages[0], "content", "") or ""
        last_human = next(
            (msg.content for msg in reversed(messages) if msg.__class__.__name__ == "HumanMessage"),
            "",
        )
        if "CommandNotification" not in last_human and "task-notification" not in last_human:
            return AIMessage(content="UNRELATED")
        if "Terminal background completion notifications require an explicit assistant followthrough." in system_text:
            return AIMessage(content="FOLLOWTHROUGH_ACK")
        return AIMessage(content="")


class _TerminalFollowthroughSilentModel:
    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        last_human = next(
            (msg.content for msg in reversed(messages) if msg.__class__.__name__ == "HumanMessage"),
            "",
        )
        if "CommandNotification" in last_human or "task-notification" in last_human:
            return AIMessage(content="")
        return AIMessage(content="UNRELATED")


class _ChatNotificationSilentModel:
    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        last_human = next(
            (msg.content for msg in reversed(messages) if msg.__class__.__name__ == "HumanMessage"),
            "",
        )
        if "New message from" in last_human and "chat_read(chat_id=" in last_human:
            return AIMessage(content="")
        return AIMessage(content="UNRELATED")


class _PromptTooLongTwiceModel:
    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        raise RuntimeError("prompt is too long")


class _QueryOkWithFailingCompactorModel:
    def bind_tools(self, tools):
        return self

    def bind(self, **kwargs):
        return self

    async def ainvoke(self, messages):
        system_text = ""
        if messages and messages[0].__class__.__name__ == "SystemMessage":
            system_text = getattr(messages[0], "content", "") or ""
        if "tasked with summarizing conversations" in system_text or "split turn" in system_text.lower():
            raise RuntimeError("compaction failed")
        return AIMessage(content="OK")


class _BridgeReactiveCompactMiddleware:
    compact_boundary_index = 1

    async def compact_messages_for_recovery(self, messages):
        return [SystemMessage(content="[Conversation Summary]\nSUMMARY")] + list(messages[-1:])


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


class _ToolThenConcurrencyLimitModel:
    def __init__(self) -> None:
        self._turn = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if self._turn == 0:
            self._turn += 1
            return AIMessage(
                content="",
                tool_calls=[{"name": "Write", "args": {"file_path": "/tmp/demo.txt", "content": "hi"}, "id": "tc-write"}],
            )
        raise RuntimeError("Concurrency limit exceeded for user, please retry later")


class _SteerAwareTerminalModel:
    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        last_human = next(
            (msg.content for msg in reversed(messages) if msg.__class__.__name__ == "HumanMessage"),
            "",
        )
        return AIMessage(content="STEER_DONE" if last_human == "Stop and just say STEER_DONE." else "UNKNOWN")


class _StopHonestyAwareModel:
    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        system_text = ""
        if messages and messages[0].__class__.__name__ == "SystemMessage":
            system_text = getattr(messages[0], "content", "") or ""
        last_human = next(
            (msg.content for msg in reversed(messages) if msg.__class__.__name__ == "HumanMessage"),
            "",
        )
        if last_human != "Stop immediately. Do not continue the old task. Reply exactly STOPPED_NOW and do not write any file.":
            return AIMessage(content="UNKNOWN")
        if "Steer requests accepted during an active run are non-preemptive." in system_text:
            return AIMessage(content="STOP_ACK_AFTER_COMPLETED_WORK")
        return AIMessage(content="STOPPED_NOW")


class _SteerCancelPoisonModel:
    def __init__(self) -> None:
        self._turn = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if self._turn == 0:
            self._turn += 1
            return AIMessage(
                content="",
                tool_calls=[{"name": "SleepTool", "args": {}, "id": "tc-sleep"}],
            )
        last_human = next(
            (msg.content for msg in reversed(messages) if msg.__class__.__name__ == "HumanMessage"),
            "",
        )
        return AIMessage(content=f"LAST_HUMAN:{last_human}")


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
        self.state = SimpleNamespace(flags=SimpleNamespace(is_compacting=False))

    def set_event_callback(self, cb) -> None:
        self._event_callback = cb

    def bind_thread(self, *, activity_sink=None) -> None:
        self._activity_sink = activity_sink

    def get_status_dict(self) -> dict[str, object]:
        return {"state": {"state": "idle", "flags": {}}}

    def transition(self, new_state) -> bool:
        valid = {
            AgentState.IDLE: {AgentState.ACTIVE},
            AgentState.ACTIVE: {AgentState.IDLE},
        }
        if new_state not in valid.get(self.current_state, set()):
            return False
        self.current_state = new_state
        return True


async def _wait_for_followthrough_text(loop: QueryLoop, thread_id: str, expected: str) -> None:
    for _ in range(100):
        state = await loop.aget_state({"configurable": {"thread_id": thread_id}})
        messages = state.values.get("messages", []) if state and state.values else []
        if any(msg.__class__.__name__ == "AIMessage" and getattr(msg, "content", None) == expected for msg in messages):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"followthrough text not observed: {expected}")


def _make_loop(
    *,
    text: str = "done",
    model=None,
    registry: ToolRegistry | None = None,
    checkpointer: _MemoryCheckpointer | None = None,
    middleware: list | None = None,
) -> QueryLoop:
    return QueryLoop(
        model=model or _NoToolModel(text=text),
        system_prompt=SystemMessage(content="sys"),
        middleware=middleware or [],
        checkpointer=checkpointer,
        registry=registry or ToolRegistry(),
        app_state=AppState(),
        runtime=None,
        bootstrap=BootstrapConfig(workspace_root=Path("/tmp"), model_name="test-model"),
        max_turns=5,
    )


def _patch_streaming_event_store(monkeypatch: pytest.MonkeyPatch) -> None:
    seq = 0

    async def fake_append_event(thread_id, run_id, event, message_id=None, run_event_repo=None):
        nonlocal seq
        seq += 1
        return seq

    async def fake_cleanup_old_runs(thread_id, keep_latest=1, run_event_repo=None):
        return 0

    monkeypatch.setattr("backend.web.services.event_store.append_event", fake_append_event)
    monkeypatch.setattr("backend.web.services.streaming_service.cleanup_old_runs", fake_cleanup_old_runs)


def _patch_direct_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_streaming_event_store(monkeypatch)
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *args, **kwargs: None)


def _make_streaming_agent(loop: QueryLoop, *, queue_manager: MessageQueueManager | None = None) -> SimpleNamespace:
    agent = SimpleNamespace(
        agent=loop,
        runtime=_StreamingRuntime(),
        storage_container=None,
    )
    if queue_manager is not None:
        agent.queue_manager = queue_manager
    return agent


def _make_streaming_app(
    tmp_path: Path,
    *,
    thread_id: str | None = None,
    agent: SimpleNamespace | None = None,
    queue_manager: MessageQueueManager | None = None,
    include_route_locks: bool = False,
) -> tuple[SimpleNamespace, MessageQueueManager]:
    queue_manager = queue_manager or MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    state = SimpleNamespace(
        display_builder=DisplayBuilder(),
        thread_tasks={},
        thread_event_buffers={},
        subagent_buffers={},
        queue_manager=queue_manager,
        thread_last_active={},
        typing_tracker=None,
    )
    if thread_id is not None and agent is not None:
        state.agent_pool = {f"{thread_id}:local": agent}
        state.thread_sandbox = {thread_id: "local"}
        state._event_loop = asyncio.get_running_loop()
    if include_route_locks:
        state.thread_locks = {}
        state.thread_locks_guard = asyncio.Lock()
    return SimpleNamespace(state=state), queue_manager


def _make_direct_streaming_context(
    tmp_path: Path,
    loop: QueryLoop,
    *,
    queue_manager: MessageQueueManager | None = None,
) -> tuple[SimpleNamespace, SimpleNamespace, ThreadEventBuffer]:
    agent = _make_streaming_agent(loop, queue_manager=queue_manager)
    app, _ = _make_streaming_app(tmp_path, queue_manager=queue_manager)
    return agent, app, ThreadEventBuffer()


def _make_route_followthrough_context(
    tmp_path: Path,
    *,
    thread_id: str,
    loop: QueryLoop,
) -> tuple[MessageQueueManager, SimpleNamespace, SimpleNamespace]:
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    agent = _make_streaming_agent(loop, queue_manager=queue_manager)
    app, _ = _make_streaming_app(tmp_path, thread_id=thread_id, agent=agent, queue_manager=queue_manager)
    _ensure_thread_handlers(agent, thread_id, app)
    return queue_manager, agent, app


async def _run_direct_notification_followthrough(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    loop: QueryLoop,
    thread_id: str,
    message: str,
    run_id: str,
    message_metadata: dict[str, str] | None = None,
) -> list[dict]:
    _patch_direct_streaming(monkeypatch)
    agent, app, thread_buf = _make_direct_streaming_context(tmp_path, loop)

    await _run_agent_to_buffer(
        agent,
        thread_id,
        message,
        app,
        False,
        thread_buf,
        run_id,
        message_metadata=message_metadata,
    )

    entries = app.state.display_builder.get_entries(thread_id)
    assert entries is not None
    return entries


def _assert_notice_then_text(entries: list[dict], notice_contains: str, expected_text: str) -> None:
    assert entries[0]["segments"][0]["type"] == "notice"
    assert notice_contains in entries[0]["segments"][0]["content"]
    assert entries[0]["segments"][1] == {"type": "text", "content": expected_text}


async def _get_local_thread_history(thread_id: str, *, agent: SimpleNamespace, app: SimpleNamespace) -> dict:
    with (
        patch.object(threads_router, "get_or_create_agent", return_value=agent),
        patch.object(threads_router, "resolve_thread_sandbox", return_value="local"),
    ):
        return await get_thread_history(thread_id, limit=20, truncate=400, user_id="u", app=app)


def _patch_fake_event_bus(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeEventBus:
        def subscribe(self, *_args, **_kwargs):
            return None

        def make_emitter(self, **_kwargs):
            async def _emit(_event):
                return None

            return _emit

    monkeypatch.setattr("backend.web.event_bus.get_event_bus", lambda: _FakeEventBus())


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
    checkpointer.store["repair-live-thread"] = {"channel_values": {"messages": [broken_ai, trailing]}}

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
async def test_get_thread_history_persists_visible_assistant_error_after_model_failure():
    checkpointer = _MemoryCheckpointer()
    registry = ToolRegistry()
    registry.register(
        ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={"name": "Write", "description": "write file"},
            handler=lambda **_: "FILE_WRITTEN",
            source="test",
        )
    )
    loop = _make_loop(
        model=_ToolThenConcurrencyLimitModel(),
        registry=registry,
        checkpointer=checkpointer,
    )
    config = {"configurable": {"thread_id": "history-visible-model-error"}}

    async for _ in loop.query(
        {"messages": [{"role": "user", "content": "write once, then continue"}]},
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
            "history-visible-model-error",
            limit=20,
            truncate=300,
            user_id="u",
            app=fake_app,
        )

    assert [item["role"] for item in history["messages"]] == ["human", "tool_call", "tool_result", "assistant"]
    assert history["messages"][-1]["text"] == "Error: Concurrency limit exceeded for user, please retry later"


@pytest.mark.asyncio
async def test_query_loop_persists_visible_terminal_followthrough_when_system_notification_resume_is_silent():
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
        "AIMessage",
    ]
    assert state.values["messages"][-2].content.startswith("<system-reminder><task-notification>")
    assert state.values["messages"][-1].content == "Background agent failed, but the followthrough assistant reply was empty."


@pytest.mark.asyncio
async def test_query_loop_persists_midrun_steer_message_into_checkpoint_state(tmp_path):
    checkpointer = _MemoryCheckpointer()
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    queue_manager.enqueue(
        "Stop and just say STEER_DONE.",
        "steer-persist-thread",
        notification_type="steer",
        source="owner",
        is_steer=True,
    )
    runtime = SimpleNamespace(events=[], emit_activity_event=lambda event: runtime.events.append(event))
    loop = _make_loop(
        model=_SteerAwareTerminalModel(),
        checkpointer=checkpointer,
        middleware=[SteeringMiddleware(queue_manager=queue_manager, agent_runtime=runtime)],
    )
    checkpointer.store["steer-persist-thread"] = {
        "channel_values": {
            "messages": [
                HumanMessage(content="Use Bash to run `sleep 20; echo LONG_PHASE_DONE`, then reply exactly ORIGINAL_DONE."),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "Bash", "args": {"command": "sleep 20; echo LONG_PHASE_DONE"}, "id": "tc-bash"}],
                ),
                ToolMessage(content="LONG_PHASE_DONE", name="Bash", tool_call_id="tc-bash"),
            ]
        }
    }

    async for _ in loop.query(None, config={"configurable": {"thread_id": "steer-persist-thread"}}):
        pass

    state = await loop.aget_state({"configurable": {"thread_id": "steer-persist-thread"}})
    persisted = state.values["messages"]

    assert [msg.__class__.__name__ for msg in persisted] == [
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
        "HumanMessage",
        "AIMessage",
    ]
    assert persisted[3].content == "Stop and just say STEER_DONE."
    assert persisted[3].metadata["source"] == "owner"
    assert persisted[3].metadata["is_steer"] is True
    assert persisted[4].content == "STEER_DONE"


@pytest.mark.asyncio
async def test_get_thread_history_rebuilds_persisted_midrun_steer_message(tmp_path):
    checkpointer = _MemoryCheckpointer()
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    queue_manager.enqueue(
        "Stop and just say STEER_DONE.",
        "steer-history-thread",
        notification_type="steer",
        source="owner",
        is_steer=True,
    )
    runtime = SimpleNamespace(events=[], emit_activity_event=lambda event: runtime.events.append(event))
    loop = _make_loop(
        model=_SteerAwareTerminalModel(),
        checkpointer=checkpointer,
        middleware=[SteeringMiddleware(queue_manager=queue_manager, agent_runtime=runtime)],
    )
    checkpointer.store["steer-history-thread"] = {
        "channel_values": {
            "messages": [
                HumanMessage(content="Use Bash to run `sleep 20; echo LONG_PHASE_DONE`, then reply exactly ORIGINAL_DONE."),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "Bash", "args": {"command": "sleep 20; echo LONG_PHASE_DONE"}, "id": "tc-bash"}],
                ),
                ToolMessage(content="LONG_PHASE_DONE", name="Bash", tool_call_id="tc-bash"),
            ]
        }
    }

    async for _ in loop.query(None, config={"configurable": {"thread_id": "steer-history-thread"}}):
        pass

    fake_agent = SimpleNamespace(agent=loop)
    fake_app = SimpleNamespace(state=SimpleNamespace())
    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
    ):
        history = await get_thread_history(
            "steer-history-thread",
            limit=20,
            truncate=300,
            user_id="u",
            app=fake_app,
        )

    assert [item["role"] for item in history["messages"]] == [
        "human",
        "tool_call",
        "tool_result",
        "human",
        "assistant",
    ]
    assert history["messages"][3]["text"] == "Stop and just say STEER_DONE."
    assert history["messages"][4]["text"] == "STEER_DONE"


@pytest.mark.asyncio
async def test_query_loop_adds_non_preemptive_steer_contract_before_terminal_reply(tmp_path):
    checkpointer = _MemoryCheckpointer()
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    queue_manager.enqueue(
        "Stop immediately. Do not continue the old task. Reply exactly STOPPED_NOW and do not write any file.",
        "steer-stop-honesty-thread",
        notification_type="steer",
        source="owner",
        is_steer=True,
    )
    runtime = SimpleNamespace(events=[], emit_activity_event=lambda event: runtime.events.append(event))
    loop = _make_loop(
        model=_StopHonestyAwareModel(),
        checkpointer=checkpointer,
        middleware=[SteeringMiddleware(queue_manager=queue_manager, agent_runtime=runtime)],
    )
    checkpointer.store["steer-stop-honesty-thread"] = {
        "channel_values": {
            "messages": [
                HumanMessage(content="Run the long bash."),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "Bash", "args": {"command": "sleep 15; echo LONG_PHASE_DONE"}, "id": "tc-bash"}],
                ),
                ToolMessage(content="LONG_PHASE_DONE", name="Bash", tool_call_id="tc-bash"),
            ]
        }
    }

    async for _ in loop.query(None, config={"configurable": {"thread_id": "steer-stop-honesty-thread"}}):
        pass

    state = await loop.aget_state({"configurable": {"thread_id": "steer-stop-honesty-thread"}})
    persisted = state.values["messages"]

    assert [msg.__class__.__name__ for msg in persisted] == [
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
        "HumanMessage",
        "AIMessage",
    ]
    assert persisted[3].content == "Stop immediately. Do not continue the old task. Reply exactly STOPPED_NOW and do not write any file."
    assert persisted[4].content == "STOP_ACK_AFTER_COMPLETED_WORK"


@pytest.mark.asyncio
async def test_cancelled_midrun_steer_persists_and_does_not_poison_next_turn(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *args, **kwargs: None)
    checkpointer = _MemoryCheckpointer()
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    runtime = _StreamingRuntime()
    tool_started = asyncio.Event()

    async def sleep_tool() -> str:
        tool_started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        return "SLEPT"

    registry = ToolRegistry()
    registry.register(
        ToolEntry(
            name="SleepTool",
            mode=ToolMode.INLINE,
            schema={"name": "SleepTool", "description": "sleep", "parameters": {}},
            handler=sleep_tool,
            source="test",
        )
    )
    loop = _make_loop(
        model=_SteerCancelPoisonModel(),
        registry=registry,
        checkpointer=checkpointer,
        middleware=[SteeringMiddleware(queue_manager=queue_manager, agent_runtime=runtime)],
    )
    agent = SimpleNamespace(
        agent=loop,
        runtime=runtime,
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
    thread_id = "steer-cancel-poison-thread"
    config = {"configurable": {"thread_id": thread_id}}

    start_agent_run(agent, thread_id, "start", app)
    task = app.state.thread_tasks[thread_id]

    await asyncio.wait_for(tool_started.wait(), timeout=2)
    queue_manager.enqueue(
        "Stop and just say STEER_DONE.",
        thread_id,
        notification_type="steer",
        source="owner",
        is_steer=True,
    )

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert queue_manager.list_queue(thread_id) == []
    assert app.state.thread_tasks.get(thread_id) is None
    assert runtime.current_state == AgentState.IDLE

    state_after_cancel = await loop.aget_state(config)
    cancelled_contents = [getattr(msg, "content", "") for msg in state_after_cancel.values["messages"]]
    assert cancelled_contents[:2] == ["start", "Stop and just say STEER_DONE."]

    async for _ in loop.query(
        {"messages": [{"role": "user", "content": "fresh user message"}]},
        config=config,
    ):
        pass

    final_state = await loop.aget_state(config)
    final_contents = [getattr(msg, "content", "") for msg in final_state.values["messages"]]
    assert final_contents == [
        "start",
        "Stop and just say STEER_DONE.",
        "fresh user message",
        "LAST_HUMAN:fresh user message",
    ]


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
async def test_get_thread_messages_idle_rebuild_replays_latest_run_error_from_event_log():
    human = HumanMessage(content="hello")
    fake_agent = SimpleNamespace(
        agent=SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={"messages": [human]}))),
        runtime=SimpleNamespace(current_state=AgentState.IDLE),
    )
    fake_app = SimpleNamespace(state=SimpleNamespace(display_builder=DisplayBuilder()))
    run_events = [
        {
            "seq": 1,
            "event": "run_start",
            "data": json.dumps(
                {
                    "thread_id": "detail-thread",
                    "run_id": "run-error-1",
                    "source": "owner",
                    "showing": True,
                }
            ),
            "message_id": None,
        },
        {
            "seq": 2,
            "event": "error",
            "data": json.dumps({"error": "quota exploded"}),
            "message_id": None,
        },
        {
            "seq": 3,
            "event": "run_done",
            "data": json.dumps({"thread_id": "detail-thread", "run_id": "run-error-1"}),
            "message_id": None,
        },
    ]

    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
        patch("backend.web.routers.threads.get_sandbox_info", return_value={"type": "local"}),
        patch("backend.web.services.event_store.get_latest_run_id", AsyncMock(return_value="run-error-1")),
        patch("backend.web.services.event_store.read_events_after", AsyncMock(return_value=run_events)),
    ):
        detail = await get_thread_messages(
            "detail-thread",
            user_id="u",
            app=fake_app,
        )

    assert detail["entries"][0]["role"] == "user"
    assert any(
        entry.get("role") == "assistant"
        and any(segment.get("type") == "text" and "quota exploded" in segment.get("content", "") for segment in entry.get("segments", []))
        for entry in detail["entries"]
    )


@pytest.mark.asyncio
async def test_cold_rebuild_surfaces_persisted_compaction_notice_in_detail_and_history():
    checkpointer = _MemoryCheckpointer()
    summary_model = MagicMock()
    summary_model.bind.return_value = summary_model
    summary_model.ainvoke = AsyncMock(return_value=AIMessage(content="SUMMARY"))
    memory = MemoryMiddleware(
        context_limit=40,
        compaction_config=SimpleNamespace(reserve_tokens=0, keep_recent_tokens=10),
        compaction_threshold=0.1,
    )
    memory.set_model(summary_model)
    loop = _make_loop(
        text="after compact",
        checkpointer=checkpointer,
        middleware=[memory],
    )
    config = {"configurable": {"thread_id": "compact-thread"}}

    history = [
        HumanMessage(content="A" * 80),
        AIMessage(content="B" * 80),
        HumanMessage(content="C" * 80),
        HumanMessage(content="hello after compact"),
    ]

    async for _ in loop.query({"messages": history}, config=config):
        pass

    fake_agent = SimpleNamespace(
        agent=loop,
        runtime=SimpleNamespace(current_state=AgentState.IDLE),
    )
    fake_app = SimpleNamespace(state=SimpleNamespace(display_builder=DisplayBuilder()))

    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
        patch("backend.web.routers.threads.get_sandbox_info", return_value={"type": "local"}),
    ):
        detail = await get_thread_messages(
            "compact-thread",
            user_id="u",
            app=fake_app,
        )
        rebuilt_history = await get_thread_history(
            "compact-thread",
            limit=20,
            truncate=300,
            user_id="u",
            app=fake_app,
        )

    assert any(
        any(segment.get("type") == "notice" and segment.get("notification_type") == "compact" for segment in entry.get("segments", []))
        for entry in detail["entries"]
        if entry.get("role") == "assistant"
    )
    assert any(
        item.get("role") == "notification" and "Conversation compacted" in item.get("text", "") for item in rebuilt_history["messages"]
    )


@pytest.mark.asyncio
async def test_cold_rebuild_surfaces_persisted_prompt_too_long_notice_after_recovery_exhausts():
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(
        model=_PromptTooLongTwiceModel(),
        checkpointer=checkpointer,
        middleware=[_BridgeReactiveCompactMiddleware()],
    )
    config = {"configurable": {"thread_id": "prompt-too-long-thread"}}

    async for _ in loop.query(
        {"messages": [{"role": "user", "content": "start"}]},
        config=config,
    ):
        pass

    fake_agent = SimpleNamespace(
        agent=loop,
        runtime=SimpleNamespace(current_state=AgentState.IDLE),
    )
    fake_app = SimpleNamespace(state=SimpleNamespace(display_builder=DisplayBuilder()))

    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
        patch("backend.web.routers.threads.get_sandbox_info", return_value={"type": "local"}),
    ):
        detail = await get_thread_messages(
            "prompt-too-long-thread",
            user_id="u",
            app=fake_app,
        )
        rebuilt_history = await get_thread_history(
            "prompt-too-long-thread",
            limit=20,
            truncate=300,
            user_id="u",
            app=fake_app,
        )

    assert any(
        any(
            segment.get("type") == "notice"
            and "Prompt is too long. Automatic recovery exhausted." in segment.get("content", "")
            for segment in entry.get("segments", [])
        )
        for entry in detail["entries"]
        if entry.get("role") == "assistant"
    )
    assert any(
        item.get("role") == "notification" and "Prompt is too long. Automatic recovery exhausted." in item.get("text", "")
        for item in rebuilt_history["messages"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_status", "result_text"),
    [
        ("completed", "CHILD_DONE"),
        ("error", "Agent failed"),
        ("cancelled", "Agent cancelled"),
    ],
)
async def test_get_thread_messages_idle_rebuild_keeps_terminal_subagent_stream_status(
    task_status: str,
    result_text: str,
):
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
            f"  <status>{task_status}</status>\n"
            "  <description>child task</description>\n"
            "  <summary>child task</summary>\n"
            f"  <result>{result_text}</result>\n"
            "</task-notification>\n"
            "</system-reminder>"
        )
    )
    notice.metadata = {"source": "system", "notification_type": "agent"}

    fake_agent = SimpleNamespace(
        agent=SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={"messages": [ai, tool, notice]}))),
        runtime=SimpleNamespace(current_state=AgentState.IDLE),
    )
    fake_app = SimpleNamespace(state=SimpleNamespace(display_builder=DisplayBuilder()))

    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
        patch("backend.web.routers.threads.get_sandbox_info", return_value={"type": "local"}),
    ):
        detail = await get_thread_messages(
            "parent-thread",
            user_id="u",
            app=fake_app,
        )

    seg = detail["entries"][0]["segments"][0]
    assert seg["step"]["subagent_stream"]["task_id"] == "task-123"
    assert seg["step"]["subagent_stream"]["thread_id"] == "subagent-task-123"
    assert seg["step"]["subagent_stream"]["status"] == task_status


@pytest.mark.asyncio
async def test_compaction_clear_then_recovery_notice_rebuilds_honestly(tmp_path):
    checkpointer = _MemoryCheckpointer()
    summary_model = MagicMock()
    summary_model.bind.return_value = summary_model
    summary_model.ainvoke = AsyncMock(return_value=AIMessage(content="SUMMARY"))

    memory = MemoryMiddleware(
        context_limit=40,
        compaction_config=SimpleNamespace(reserve_tokens=0, keep_recent_tokens=10),
        compaction_threshold=0.1,
        db_path=tmp_path / "compaction-lifecycle.db",
    )
    memory.set_model(summary_model)
    config = {"configurable": {"thread_id": "compaction-lifecycle-thread"}}
    compact_loop = _make_loop(
        text="after compact",
        checkpointer=checkpointer,
        middleware=[memory],
    )

    history = [
        HumanMessage(content="A" * 80),
        AIMessage(content="B" * 80),
        HumanMessage(content="C" * 80),
        HumanMessage(content="hello after compact"),
    ]

    async for _ in compact_loop.query({"messages": history}, config=config):
        pass

    assert memory.summary_store is not None
    assert memory.summary_store.get_latest_summary("compaction-lifecycle-thread") is not None

    fake_app = SimpleNamespace(state=SimpleNamespace(display_builder=DisplayBuilder()))
    fake_agent = SimpleNamespace(
        agent=compact_loop,
        runtime=SimpleNamespace(current_state=AgentState.IDLE),
    )

    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
        patch("backend.web.routers.threads.get_sandbox_info", return_value={"type": "local"}),
    ):
        compact_detail = await get_thread_messages(
            "compaction-lifecycle-thread",
            user_id="u",
            app=fake_app,
        )
        compact_history = await get_thread_history(
            "compaction-lifecycle-thread",
            limit=20,
            truncate=300,
            user_id="u",
            app=fake_app,
        )

    assert any(
        item.get("role") == "notification" and "Conversation compacted" in item.get("text", "") for item in compact_history["messages"]
    )
    assert any(
        any(
            segment.get("type") == "notice" and "Conversation compacted" in segment.get("content", "")
            for segment in entry.get("segments", [])
        )
        for entry in compact_detail["entries"]
        if entry.get("role") == "assistant"
    )

    await compact_loop.aclear("compaction-lifecycle-thread")

    assert memory.summary_store.get_latest_summary("compaction-lifecycle-thread") is None

    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
        patch("backend.web.routers.threads.get_sandbox_info", return_value={"type": "local"}),
    ):
        cleared_detail = await get_thread_messages(
            "compaction-lifecycle-thread",
            user_id="u",
            app=fake_app,
        )
        cleared_history = await get_thread_history(
            "compaction-lifecycle-thread",
            limit=20,
            truncate=300,
            user_id="u",
            app=fake_app,
        )

    assert cleared_detail["entries"] == []
    assert cleared_history["messages"] == []

    recovery_loop = _make_loop(
        model=_PromptTooLongTwiceModel(),
        checkpointer=checkpointer,
        middleware=[_BridgeReactiveCompactMiddleware()],
    )
    recovery_agent = SimpleNamespace(
        agent=recovery_loop,
        runtime=SimpleNamespace(current_state=AgentState.IDLE),
    )

    async for _ in recovery_loop.query(
        {"messages": [{"role": "user", "content": "start"}]},
        config=config,
    ):
        pass

    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=recovery_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
        patch("backend.web.routers.threads.get_sandbox_info", return_value={"type": "local"}),
    ):
        recovery_detail = await get_thread_messages(
            "compaction-lifecycle-thread",
            user_id="u",
            app=fake_app,
        )
        recovery_history = await get_thread_history(
            "compaction-lifecycle-thread",
            limit=20,
            truncate=300,
            user_id="u",
            app=fake_app,
        )

    notices = [item for item in recovery_history["messages"] if item.get("role") == "notification"]
    assert notices == [
        {
            "role": "notification",
            "text": "Prompt is too long. Automatic recovery exhausted. Clear the thread or start a new one.",
        }
    ]
    assert not any("Conversation compacted" in item.get("text", "") for item in recovery_history["messages"])
    assert any(
        any(
            segment.get("type") == "notice"
            and "Prompt is too long. Automatic recovery exhausted." in segment.get("content", "")
            for segment in entry.get("segments", [])
        )
        for entry in recovery_detail["entries"]
        if entry.get("role") == "assistant"
    )


@pytest.mark.asyncio
async def test_cold_rebuild_surfaces_compaction_breaker_notice_after_repeated_failures(tmp_path):
    checkpointer = _MemoryCheckpointer()
    model = _QueryOkWithFailingCompactorModel()
    memory = MemoryMiddleware(
        context_limit=10000,
        compaction_threshold=0.5,
        db_path=tmp_path / "compaction-breaker.db",
        compaction_config=SimpleNamespace(reserve_tokens=0, keep_recent_tokens=10),
    )
    memory.set_model(model)
    loop = _make_loop(
        model=model,
        checkpointer=checkpointer,
        middleware=[memory],
    )
    config = {"configurable": {"thread_id": "compaction-breaker-thread"}}

    for attempt in range(3):
        async for _ in loop.query(
            {
                "messages": [
                    {"role": "user", "content": "A" * 8000},
                    {"role": "assistant", "content": "B" * 8000},
                    {"role": "user", "content": f"start {attempt} " + ("C" * 8000)},
                ]
            },
            config=config,
        ):
            pass

    fake_agent = SimpleNamespace(
        agent=loop,
        runtime=SimpleNamespace(current_state=AgentState.IDLE),
    )
    fake_app = SimpleNamespace(state=SimpleNamespace(display_builder=DisplayBuilder()))

    with (
        patch("backend.web.routers.threads.get_or_create_agent", return_value=fake_agent),
        patch("backend.web.routers.threads.resolve_thread_sandbox", return_value="local"),
        patch("backend.web.routers.threads.get_sandbox_info", return_value={"type": "local"}),
    ):
        detail = await get_thread_messages(
            "compaction-breaker-thread",
            user_id="u",
            app=fake_app,
        )
        rebuilt_history = await get_thread_history(
            "compaction-breaker-thread",
            limit=50,
            truncate=300,
            user_id="u",
            app=fake_app,
        )

    assert any(
        entry.get("role") == "assistant"
        and any(
            seg.get("type") == "notice"
            and "Automatic compaction disabled for this thread after repeated failures." in seg.get("content", "")
            for seg in entry.get("segments", [])
        )
        for entry in detail["entries"]
    )
    assert any(
        item.get("role") == "notification"
        and "Automatic compaction disabled for this thread after repeated failures." in item.get("text", "")
        for item in rebuilt_history["messages"]
    )


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
async def test_run_agent_to_buffer_persists_terminal_notifications_before_assistant_followthrough(monkeypatch, tmp_path):
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
        "AIMessage",
    ]
    assert "BG_OK" in state.values["messages"][0].content
    assert "Agent failed" in state.values["messages"][1].content
    assert state.values["messages"][2].content == "done"


@pytest.mark.asyncio
async def test_run_agent_to_buffer_resumes_graph_for_terminal_background_notifications(monkeypatch, tmp_path):
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

    assert graph.astream_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "thread_id",
        "run_id",
        "message",
        "message_metadata",
        "notice_contains",
        "expected_text",
    ),
    [
        (
            "thread-terminal-followthrough",
            "run-terminal-followthrough",
            "<system-reminder><task-notification><status>completed</status><result>BG_OK</result></task-notification></system-reminder>",
            {"source": "system", "notification_type": "agent"},
            "BG_OK",
            "AFTER_BG_DONE",
        ),
        (
            "thread-command-followthrough",
            "run-command-followthrough",
            "<system-reminder><CommandNotification><Status>completed</Status><Output>42</Output></CommandNotification></system-reminder>",
            {"source": "system", "notification_type": "command"},
            "CommandNotification",
            "AFTER_COMMAND_DONE",
        ),
        (
            "thread-command-cancel-followthrough",
            "run-command-cancel-followthrough",
            '<CommandNotification task_id="cmd-x" status="cancelled"><Status>cancelled</Status><Description>cancelled task</Description></CommandNotification>',
            {"source": "system", "notification_type": "command"},
            "cancelled",
            "AFTER_COMMAND_CANCELLED",
        ),
    ],
)
async def test_run_agent_to_buffer_surfaces_notice_then_assistant_followthrough(
    monkeypatch,
    tmp_path,
    thread_id: str,
    run_id: str,
    message: str,
    message_metadata: dict[str, str],
    notice_contains: str,
    expected_text: str,
):
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(text=expected_text, checkpointer=checkpointer)

    entries = await _run_direct_notification_followthrough(
        monkeypatch,
        tmp_path,
        loop=loop,
        thread_id=thread_id,
        message=message,
        run_id=run_id,
        message_metadata=message_metadata,
    )

    _assert_notice_then_text(entries, notice_contains, expected_text)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("thread_id", "message", "notification_type", "expected_notice", "expected_text"),
    [
        (
            "thread-route-followthrough",
            "<system-reminder><CommandNotification><Status>completed</Status><Output>42</Output></CommandNotification></system-reminder>",
            "command",
            "CommandNotification",
            "AFTER_QUEUE_WAKE",
        ),
        (
            "thread-route-agent-followthrough",
            "<system-reminder><task-notification><status>completed</status><summary>Simple background tool test</summary><result>Simple Background Tool Test Done</result></task-notification></system-reminder>",
            "agent",
            "Simple Background Tool Test Done",
            "AFTER_AGENT_WAKE",
        ),
        (
            "thread-route-agent-error-followthrough",
            "<system-reminder><task-notification><status>error</status><summary>Simple background tool test</summary><result>Agent failed</result></task-notification></system-reminder>",
            "agent",
            "Agent failed",
            "AFTER_AGENT_ERROR_WAKE",
        ),
    ],
)
async def test_queue_wake_handler_starts_terminal_followthrough_run(
    monkeypatch,
    tmp_path,
    thread_id: str,
    message: str,
    notification_type: str,
    expected_notice: str,
    expected_text: str,
):
    _patch_streaming_event_store(monkeypatch)

    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(text=expected_text, checkpointer=checkpointer)
    queue_manager, agent, app = _make_route_followthrough_context(tmp_path, thread_id=thread_id, loop=loop)

    queue_manager.enqueue(
        message,
        thread_id,
        notification_type=notification_type,
        source="system",
    )

    await _wait_for_followthrough_text(loop, thread_id, expected_text)
    history = await _get_local_thread_history(thread_id, agent=agent, app=app)

    assert [item["role"] for item in history["messages"]] == ["notification", "assistant"]
    assert expected_notice in history["messages"][0]["text"]
    assert history["messages"][1]["text"] == expected_text


@pytest.mark.asyncio
async def test_cancelled_task_notification_wakes_followthrough_run(monkeypatch, tmp_path):
    _patch_streaming_event_store(monkeypatch)
    _patch_fake_event_bus(monkeypatch)

    thread_id = "thread-route-cancel-followthrough"
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(text="AFTER_CANCEL_WAKE", checkpointer=checkpointer)
    queue_manager, agent, app = _make_route_followthrough_context(tmp_path, thread_id=thread_id, loop=loop)
    run = SimpleNamespace(is_done=True, description="cancelled task", command="echo hi")
    await threads_router._notify_task_cancelled(app, thread_id, "cmd-cancel", run)

    await _wait_for_followthrough_text(loop, thread_id, "AFTER_CANCEL_WAKE")
    history = await _get_local_thread_history(thread_id, agent=agent, app=app)
    assert [item["role"] for item in history["messages"]] == ["notification", "assistant"]
    assert "cancelled" in history["messages"][0]["text"]
    assert history["messages"][1]["text"] == "AFTER_CANCEL_WAKE"


@pytest.mark.asyncio
async def test_send_message_route_then_agent_terminal_notification_reenters_followthrough(monkeypatch, tmp_path):
    _patch_streaming_event_store(monkeypatch)

    thread_id = "thread-route-send-message-followthrough"
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(model=_TurnTextModel("OWNER_OK", "AFTER_AGENT_ROUTE_WAKE"), checkpointer=checkpointer)
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    agent = _make_streaming_agent(loop, queue_manager=queue_manager)
    app, _ = _make_streaming_app(
        tmp_path,
        thread_id=thread_id,
        agent=agent,
        queue_manager=queue_manager,
        include_route_locks=True,
    )

    with (
        patch("backend.web.services.agent_pool.get_or_create_agent", AsyncMock(return_value=agent)),
        patch("backend.web.services.agent_pool.resolve_thread_sandbox", return_value="local"),
    ):
        result = await threads_router.send_message(
            thread_id,
            SendMessageRequest(message="start owner turn"),
            user_id="u",
            app=app,
        )

    assert result["status"] == "started"
    await _wait_for_followthrough_text(loop, thread_id, "OWNER_OK")

    queue_manager.enqueue(
        "<system-reminder><task-notification><status>completed</status><summary>Simple background tool test</summary><result>Simple Background Tool Test Done</result></task-notification></system-reminder>",
        thread_id,
        notification_type="agent",
        source="system",
    )

    await _wait_for_followthrough_text(loop, thread_id, "AFTER_AGENT_ROUTE_WAKE")

    with (
        patch.object(threads_router, "get_or_create_agent", return_value=agent),
        patch.object(threads_router, "resolve_thread_sandbox", return_value="local"),
    ):
        history = await get_thread_history(thread_id, limit=20, truncate=400, user_id="u", app=app)

    assert [item["role"] for item in history["messages"]] == ["human", "assistant", "notification", "assistant"]
    assert history["messages"][0]["text"] == "start owner turn"
    assert history["messages"][1]["text"] == "OWNER_OK"
    assert "Simple Background Tool Test Done" in history["messages"][2]["text"]
    assert history["messages"][3]["text"] == "AFTER_AGENT_ROUTE_WAKE"


@pytest.mark.asyncio
async def test_run_agent_to_buffer_adds_terminal_followthrough_system_note_to_prevent_silent_completion(monkeypatch, tmp_path):
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(model=_TerminalFollowthroughPromptAwareModel(), checkpointer=checkpointer)
    entries = await _run_direct_notification_followthrough(
        monkeypatch,
        tmp_path,
        loop=loop,
        thread_id="thread-terminal-followthrough-note",
        message="<system-reminder><CommandNotification><Status>completed</Status><Output>42</Output></CommandNotification></system-reminder>",
        run_id="run-terminal-followthrough-note",
        message_metadata={"source": "system", "notification_type": "command"},
    )
    _assert_notice_then_text(entries, "CommandNotification", "FOLLOWTHROUGH_ACK")


@pytest.mark.asyncio
async def test_run_agent_to_buffer_turns_silent_terminal_reentry_into_visible_followthrough(monkeypatch, tmp_path):
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(model=_TerminalFollowthroughSilentModel(), checkpointer=checkpointer)
    entries = await _run_direct_notification_followthrough(
        monkeypatch,
        tmp_path,
        loop=loop,
        thread_id="thread-terminal-followthrough-silent",
        message="<system-reminder><CommandNotification><Status>completed</Status><Output>42</Output></CommandNotification></system-reminder>",
        run_id="run-terminal-followthrough-silent",
        message_metadata={"source": "system", "notification_type": "command"},
    )
    _assert_notice_then_text(
        entries,
        "CommandNotification",
        "Background command completed, but the followthrough assistant reply was empty.",
    )


@pytest.mark.asyncio
async def test_run_agent_to_buffer_turns_silent_chat_notification_into_visible_followthrough(monkeypatch, tmp_path):
    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(model=_ChatNotificationSilentModel(), checkpointer=checkpointer)
    entries = await _run_direct_notification_followthrough(
        monkeypatch,
        tmp_path,
        loop=loop,
        thread_id="thread-chat-followthrough-silent",
        message='<system-reminder>\nNew message from alice in chat chat-123 (1 unread).\nRead it with chat_read(chat_id="chat-123").\nReply with chat_send(chat_id="chat-123", content="...").\nDo not treat your normal assistant text as a chat reply.\n</system-reminder>',
        run_id="run-chat-followthrough-silent",
        message_metadata={"source": "external", "notification_type": "chat"},
    )
    _assert_notice_then_text(
        entries,
        'chat_read(chat_id="chat-123")',
        'I received a chat notification, but the followthrough assistant reply was empty. Read it with chat_read(chat_id="chat-123") before deciding whether to reply.',
    )


@pytest.mark.asyncio
async def test_run_agent_to_buffer_tags_display_delta_with_source_seq(monkeypatch, tmp_path):
    _patch_streaming_event_store(monkeypatch)
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *args, **kwargs: None)

    checkpointer = _MemoryCheckpointer()
    loop = _make_loop(model=_NoToolModel("SEQ_OK"), checkpointer=checkpointer)
    agent, app, thread_buf = _make_direct_streaming_context(tmp_path, loop)

    await _run_agent_to_buffer(
        agent,
        "thread-display-delta-seq",
        "hello",
        app,
        False,
        thread_buf,
        "run-display-delta-seq",
    )

    events, _ = await thread_buf.read_with_timeout(0, timeout=0.01)
    assert events is not None
    display_deltas = [json.loads(event["data"]) for event in events if event.get("event") == "display_delta"]
    assert display_deltas
    assert all(isinstance(delta.get("_seq"), int) for delta in display_deltas)


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
