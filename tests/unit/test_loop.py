"""Unit tests for core.runtime.loop QueryLoop."""

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from core.runtime.middleware.memory import MemoryMiddleware
from core.runtime.middleware import AgentMiddleware
from core.runtime.loop import QueryLoop, _StreamingToolExecutor
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from core.runtime.state import AppState, BootstrapConfig
from storage.providers.sqlite.kernel import connect_sqlite_async


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_registry(*entries):
    reg = ToolRegistry()
    for e in entries:
        reg.register(e)
    return reg


def make_loop(model, registry=None, middleware=None, max_turns=10, app_state=None, runtime=None):
    return QueryLoop(
        model=model,
        system_prompt=SystemMessage(content="You are a test assistant."),
        middleware=middleware or [],
        checkpointer=None,
        registry=registry or make_registry(),
        app_state=app_state,
        runtime=runtime,
        bootstrap=BootstrapConfig(workspace_root=Path("/tmp"), model_name="test-model"),
        max_turns=max_turns,
    )


class _MemoryCheckpointer:
    def __init__(self):
        self.store = {}

    async def aget(self, cfg):
        return self.store.get(cfg["configurable"]["thread_id"])

    async def aput(self, cfg, checkpoint, metadata, new_versions):
        self.store[cfg["configurable"]["thread_id"]] = checkpoint


def mock_model_no_tools(text="Hello!"):
    """Model that returns a plain AIMessage (no tool calls)."""
    ai_msg = AIMessage(content=text)
    model = MagicMock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(return_value=ai_msg)
    return model


def mock_model_with_tool_call(tool_name="echo", args=None, call_id="tc-1", then_text="Done"):
    """Model that first responds with a tool call, then responds with plain text."""
    args = args or {"message": "hi"}
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{"name": tool_name, "args": args, "id": call_id}],
    )
    final_msg = AIMessage(content=then_text)
    model = MagicMock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(side_effect=[tool_call_msg, final_msg])
    return model


def mock_model_with_two_tool_turns():
    first = AIMessage(content="", tool_calls=[{"name": "echo", "args": {"message": "one"}, "id": "tc-1"}])
    second = AIMessage(content="", tool_calls=[{"name": "echo", "args": {"message": "two"}, "id": "tc-2"}])
    final = AIMessage(content="done")
    model = MagicMock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(side_effect=[first, second, final])
    return model


def test_tool_use_context_get_app_state_is_live_closure():
    app_state = AppState(turn_count=1)
    loop = make_loop(mock_model_no_tools(), app_state=app_state)

    ctx = loop._build_tool_use_context([])
    assert ctx is not None
    assert ctx.get_app_state().turn_count == 1

    app_state.set_state(lambda prev: prev.model_copy(update={"turn_count": 7}))

    assert ctx.get_app_state().turn_count == 7


def test_tool_use_context_session_refs_persist_across_turns():
    app_state = AppState()
    loop = make_loop(mock_model_no_tools(), app_state=app_state)

    ctx1 = loop._build_tool_use_context([HumanMessage(content="one")])
    ctx2 = loop._build_tool_use_context([HumanMessage(content="two")])

    assert ctx1 is not None
    assert ctx2 is not None

    ctx1.discovered_skill_names.add("skill-a")
    ctx1.loaded_nested_memory_paths.add("/tmp/memory.md")
    ctx1.read_file_state["/tmp/file.py"] = {"partial": False}

    assert ctx2.discovered_skill_names is ctx1.discovered_skill_names
    assert ctx2.loaded_nested_memory_paths is ctx1.loaded_nested_memory_paths
    assert ctx2.read_file_state is ctx1.read_file_state
    assert "skill-a" in ctx2.discovered_skill_names
    assert "/tmp/memory.md" in ctx2.loaded_nested_memory_paths
    assert "/tmp/file.py" in ctx2.read_file_state


def test_tool_use_context_turn_refs_are_fresh_per_turn():
    app_state = AppState()
    loop = make_loop(mock_model_no_tools(), app_state=app_state)

    ctx1 = loop._build_tool_use_context([HumanMessage(content="one")])
    ctx2 = loop._build_tool_use_context([HumanMessage(content="two")])

    assert ctx1 is not None
    assert ctx2 is not None

    ctx1.nested_memory_attachment_triggers.add("memo-a")

    assert ctx2.nested_memory_attachment_triggers == set()
    assert ctx2.nested_memory_attachment_triggers is not ctx1.nested_memory_attachment_triggers


class _CaptureTurnLocalStateMiddleware(AgentMiddleware):
    def __init__(self):
        self.turn_ids = []
        self.trigger_snapshots = []

    async def awrap_tool_call(self, request, handler):
        self.turn_ids.append(request.state.turn_id)
        self.trigger_snapshots.append(set(request.state.nested_memory_attachment_triggers))
        if len(self.turn_ids) == 1:
            request.state.nested_memory_attachment_triggers.add("first-turn-mark")
        return await handler(request)


@pytest.mark.asyncio
async def test_query_loop_rebuilds_turn_local_tool_context_each_tool_turn():
    model = mock_model_with_two_tool_turns()

    def echo_handler(message: str) -> str:
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "echo", "parameters": {}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=False,
    )
    capture = _CaptureTurnLocalStateMiddleware()
    loop = make_loop(model, registry=make_registry(entry), middleware=[capture], app_state=AppState())

    async for _ in loop.astream({"messages": [{"role": "user", "content": "two turns"}]}):
        pass

    assert len(capture.turn_ids) == 2
    assert capture.turn_ids[0] != capture.turn_ids[1]
    assert capture.trigger_snapshots == [set(), set()]


# ---------------------------------------------------------------------------
# Tests: no tool calls → single agent chunk
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_tool_calls_yields_one_agent_chunk():
    model = mock_model_no_tools("Hello world")
    loop = make_loop(model)

    chunks = []
    async for chunk in loop.astream({"messages": [{"role": "user", "content": "hi"}]}):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert "agent" in chunks[0]
    msgs = chunks[0]["agent"]["messages"]
    assert len(msgs) == 1
    assert msgs[0].content == "Hello world"


@pytest.mark.asyncio
async def test_no_tool_calls_model_called_once():
    model = mock_model_no_tools()
    loop = make_loop(model)

    async for _ in loop.astream({"messages": [{"role": "user", "content": "hi"}]}):
        pass

    assert model.ainvoke.call_count == 1


@pytest.mark.asyncio
async def test_query_loop_clear_resets_turn_state_but_preserves_accumulators():
    model = mock_model_no_tools("after clear")
    checkpointer = _MemoryCheckpointer()
    app_state = AppState(total_cost=1.25, tool_overrides={"Bash": False})
    bootstrap = BootstrapConfig(workspace_root=Path("/tmp"), model_name="test-model")
    loop = QueryLoop(
        model=model,
        system_prompt=SystemMessage(content="You are a test assistant."),
        middleware=[],
        checkpointer=checkpointer,
        registry=make_registry(),
        app_state=app_state,
        runtime=None,
        bootstrap=bootstrap,
        max_turns=10,
    )

    async for _ in loop.query(
        {"messages": [{"role": "user", "content": "hi"}]},
        config={"configurable": {"thread_id": "clear-thread"}},
    ):
        pass

    loop._tool_read_file_state["/tmp/file.py"] = {"partial": False}
    loop._tool_loaded_nested_memory_paths.add("/tmp/memory.md")
    loop._tool_discovered_skill_names.add("skill-a")
    old_session_id = bootstrap.session_id

    await loop.aclear("clear-thread")

    assert checkpointer.store["clear-thread"]["channel_values"]["messages"] == []
    assert app_state.messages == []
    assert app_state.turn_count == 0
    assert app_state.compact_boundary_index == 0
    assert app_state.total_cost == 1.25
    assert app_state.tool_overrides == {"Bash": False}
    assert loop._tool_read_file_state == {}
    assert loop._tool_loaded_nested_memory_paths == set()
    assert loop._tool_discovered_skill_names == set()
    assert bootstrap.session_id != old_session_id
    assert bootstrap.parent_session_id == old_session_id


@pytest.mark.asyncio
async def test_query_loop_replays_messages_with_real_async_sqlite_saver():
    db_path = Path(tempfile.mkdtemp()) / "checkpoints.db"
    conn = await connect_sqlite_async(db_path)
    saver = AsyncSqliteSaver(conn)
    await saver.setup()

    try:
        model = mock_model_no_tools("persist me")
        loop = QueryLoop(
            model=model,
            system_prompt=SystemMessage(content="You are a test assistant."),
            middleware=[],
            checkpointer=saver,
            registry=make_registry(),
            app_state=AppState(),
            runtime=None,
            bootstrap=BootstrapConfig(workspace_root=Path("/tmp"), model_name="test-model"),
            max_turns=10,
        )

        async for _ in loop.query(
            {"messages": [{"role": "user", "content": "first"}]},
            config={"configurable": {"thread_id": "persist-thread"}},
        ):
            pass

        reloaded = await loop._load_messages("persist-thread")
        assert [msg.content for msg in reloaded] == ["first", "persist me"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_query_loop_aclear_wipes_real_async_sqlite_saver_history():
    db_path = Path(tempfile.mkdtemp()) / "checkpoints.db"
    conn = await connect_sqlite_async(db_path)
    saver = AsyncSqliteSaver(conn)
    await saver.setup()

    try:
        model = mock_model_no_tools("persist me")
        loop = QueryLoop(
            model=model,
            system_prompt=SystemMessage(content="You are a test assistant."),
            middleware=[],
            checkpointer=saver,
            registry=make_registry(),
            app_state=AppState(total_cost=1.25),
            runtime=None,
            bootstrap=BootstrapConfig(workspace_root=Path("/tmp"), model_name="test-model", total_cost_usd=1.25),
            max_turns=10,
        )

        async for _ in loop.query(
            {"messages": [{"role": "user", "content": "first"}]},
            config={"configurable": {"thread_id": "clear-real-thread"}},
        ):
            pass

        assert [msg.content for msg in await loop._load_messages("clear-real-thread")] == ["first", "persist me"]

        await loop.aclear("clear-real-thread")

        assert await loop._load_messages("clear-real-thread") == []
        assert loop._app_state is not None
        assert loop._app_state.total_cost == 1.25
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Tests: with tool calls → agent chunk + tools chunk
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_call_yields_agent_then_tools():
    model = mock_model_with_tool_call()

    # Register a simple echo tool
    def echo_handler(message: str) -> str:
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "echo", "parameters": {"type": "object", "properties": {}}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=True,
    )
    registry = make_registry(entry)
    loop = make_loop(model, registry=registry)

    chunks = []
    async for chunk in loop.astream({"messages": [{"role": "user", "content": "call echo"}]}):
        chunks.append(chunk)

    # First chunk: agent (with tool_calls)
    # Second chunk: tools (ToolMessage results)
    # Third chunk: agent (final text response)
    agent_chunks = [c for c in chunks if "agent" in c]
    tools_chunks = [c for c in chunks if "tools" in c]

    assert len(agent_chunks) >= 1
    assert len(tools_chunks) >= 1

    # Tool result should be a ToolMessage
    tool_msgs = tools_chunks[0]["tools"]["messages"]
    assert len(tool_msgs) == 1
    assert isinstance(tool_msgs[0], ToolMessage)


@pytest.mark.asyncio
async def test_tool_call_result_content():
    model = mock_model_with_tool_call(tool_name="echo", args={"message": "test-val"})

    def echo_handler(message: str) -> str:
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "d", "parameters": {}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=False,
    )
    loop = make_loop(model, registry=make_registry(entry))

    tool_results = []
    async for chunk in loop.astream({"messages": [{"role": "user", "content": "x"}]}):
        if "tools" in chunk:
            tool_results.extend(chunk["tools"]["messages"])

    assert len(tool_results) == 1
    assert "echo: test-val" in tool_results[0].content


def test_tool_concurrency_safety_does_not_infer_from_read_only():
    entry = ToolEntry(
        name="readonly_serial",
        mode=ToolMode.INLINE,
        schema={"name": "readonly_serial", "description": "d", "parameters": {}},
        handler=lambda: "ok",
        source="test",
        is_read_only=True,
        is_concurrency_safe=False,
    )
    loop = make_loop(mock_model_no_tools(), registry=make_registry(entry))

    assert loop._tool_is_concurrency_safe({"name": "readonly_serial", "args": {}}) is False


# ---------------------------------------------------------------------------
# Tests: max_turns guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_turns_stops_loop():
    """Agent that always calls a tool should stop at max_turns."""

    def noop_handler() -> str:
        return "ok"

    entry = ToolEntry(
        name="noop",
        mode=ToolMode.INLINE,
        schema={"name": "noop", "description": "d", "parameters": {}},
        handler=noop_handler,
        source="test",
        is_concurrency_safe=True,
    )

    # Build a model that always returns a tool call
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{"name": "noop", "args": {}, "id": "tc-1"}],
    )
    model = MagicMock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(return_value=tool_call_msg)

    loop = make_loop(model, registry=make_registry(entry), max_turns=3)

    chunks = []
    async for chunk in loop.astream({"messages": [{"role": "user", "content": "go"}]}):
        chunks.append(chunk)

    # Should stop after 3 turns (3 agent + 3 tool chunks = 6 total)
    assert len(chunks) <= 6
    assert model.ainvoke.call_count == 3


# ---------------------------------------------------------------------------
# Tests: input parsing
# ---------------------------------------------------------------------------

def test_parse_input_dict_messages():
    msgs = QueryLoop._parse_input({"messages": [{"role": "user", "content": "hello"}]})
    assert len(msgs) == 1
    assert isinstance(msgs[0], HumanMessage)
    assert msgs[0].content == "hello"


def test_parse_input_langchain_messages():
    human = HumanMessage(content="hi")
    msgs = QueryLoop._parse_input({"messages": [human]})
    assert msgs[0] is human


def test_parse_input_empty():
    assert QueryLoop._parse_input({}) == []
    assert QueryLoop._parse_input({"messages": []}) == []


@pytest.mark.asyncio
async def test_query_loop_syncs_app_state_on_completion():
    model = mock_model_no_tools("AppState wired")
    app_state = AppState(compact_boundary_index=99)
    loop = make_loop(model, app_state=app_state, runtime=SimpleNamespace(cost=1.25))

    async for _ in loop.query({"messages": [{"role": "user", "content": "sync"}]}):
        pass

    assert app_state.turn_count == 1
    assert app_state.total_cost == 1.25
    assert app_state.compact_boundary_index == 0
    assert len(app_state.messages) == 2
    assert app_state.messages[0].content == "sync"
    assert app_state.messages[1].content == "AppState wired"


@pytest.mark.asyncio
async def test_query_loop_does_not_decrease_total_cost_when_runtime_reports_less():
    model = mock_model_no_tools("cost stays monotonic")
    app_state = AppState(total_cost=1.25)
    bootstrap = BootstrapConfig(workspace_root=Path("/tmp"), model_name="test-model", total_cost_usd=1.25)
    loop = QueryLoop(
        model=model,
        system_prompt=SystemMessage(content="You are a test assistant."),
        middleware=[],
        checkpointer=None,
        registry=make_registry(),
        app_state=app_state,
        runtime=SimpleNamespace(cost=0.0),
        bootstrap=bootstrap,
        max_turns=10,
    )

    async for _ in loop.query({"messages": [{"role": "user", "content": "sync"}]}):
        pass

    assert app_state.total_cost == 1.25
    assert bootstrap.total_cost_usd == 1.25


@pytest.mark.asyncio
async def test_query_loop_resets_dirty_app_state_turn_count_between_runs():
    model = mock_model_no_tools("fresh")
    app_state = AppState(turn_count=99, compact_boundary_index=7)
    loop = make_loop(model, app_state=app_state, runtime=SimpleNamespace(cost=0.0))

    first = await loop.ainvoke({"messages": [{"role": "user", "content": "hi"}]})
    second = await loop.ainvoke({"messages": [{"role": "user", "content": "again"}]})

    assert first["reason"] == "completed"
    assert second["reason"] == "completed"
    assert app_state.turn_count == 1
    assert app_state.compact_boundary_index == 0
    assert len(app_state.messages) == 2


@pytest.mark.asyncio
async def test_query_loop_refreshes_tools_between_tool_turns():
    events: list[str] = []

    async def refresh_tools() -> None:
        events.append("refresh")

    def echo_handler(message: str) -> str:
        events.append("tool")
        return f"echo: {message}"

    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{"name": "echo", "args": {"message": "hi"}, "id": "tc-1"}],
    )
    final_msg = AIMessage(content="done")
    model = MagicMock()
    model.bind_tools.return_value = model

    async def ainvoke_side_effect(*args, **kwargs):
        if not events:
            events.append("model-1")
            return tool_call_msg
        assert events == ["model-1", "tool", "refresh"]
        events.append("model-2")
        return final_msg

    model.ainvoke = AsyncMock(side_effect=ainvoke_side_effect)

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "echo", "parameters": {"type": "object", "properties": {}}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(model, registry=make_registry(entry))
    loop._refresh_tools = refresh_tools

    async for _ in loop.query({"messages": [{"role": "user", "content": "call echo"}]}):
        pass

    assert events == ["model-1", "tool", "refresh", "model-2"]


@pytest.mark.asyncio
async def test_streaming_overlap_snapshots_reused_live_chunks_before_final_aggregation():
    class ReusedChunkModel:
        def bind_tools(self, tools):
            return self

        async def astream(self, messages):
            chunk = AIMessageChunk(
                content="",
                response_metadata={"model_provider": "openai"},
                id="shared-chunk",
                tool_calls=[],
                invalid_tool_calls=[],
                tool_call_chunks=[],
            )
            yield chunk
            chunk.content = "HEL"
            yield chunk
            chunk.content = "LO"
            yield chunk
            chunk.content = ""
            chunk.usage_metadata = {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
            yield chunk
            chunk.chunk_position = "last"
            yield chunk

    loop = make_loop(ReusedChunkModel())

    agent_messages = []
    async for event in loop.query({"messages": [{"role": "user", "content": "hi"}]}):
        if "agent" in event:
            agent_messages.extend(event["agent"]["messages"])

    assert len(agent_messages) == 1
    assert agent_messages[0].content == "HELLO"
    assert agent_messages[0].usage_metadata == {
        "input_tokens": 10,
        "output_tokens": 2,
        "total_tokens": 12,
    }


class _CaptureToolContextMiddleware:
    def __init__(self):
        self.messages = None
        self.boundary = None

    async def awrap_tool_call(self, request, handler):
        self.messages = list(request.state.messages)
        self.boundary = request.state.get_app_state().compact_boundary_index
        return await handler(request)


@pytest.mark.asyncio
async def test_query_loop_syncs_tool_context_messages_to_query_time_array():
    capture = _CaptureToolContextMiddleware()
    model = mock_model_with_tool_call(tool_name="echo", args={"message": "ctx"}, then_text="done")

    def echo_handler(message: str) -> str:
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "echo", "parameters": {}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(entry),
        middleware=[capture],
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    async for _ in loop.query({"messages": [{"role": "user", "content": "call echo"}]}):
        pass

    assert capture.messages is not None
    assert len(capture.messages) == 1
    assert capture.messages[0].content == "call echo"


class _SummaryBoundaryMiddleware:
    def __init__(self, boundary_index: int):
        self.boundary_index = boundary_index
        self.compact_boundary_index = boundary_index

    async def awrap_model_call(self, request, handler):
        rewritten = [SystemMessage(content="summary")] + list(request.messages[self.boundary_index :])
        return await handler(request.override(messages=rewritten))


class _ReactiveCompactMiddleware:
    compact_boundary_index = 2

    async def compact_messages_for_recovery(self, messages):
        return [SystemMessage(content="[Conversation Summary]\nSUMMARY")] + list(messages[-1:])


class _CollapseDrainMiddleware:
    def __init__(self):
        self.calls = 0

    async def recover_from_overflow(self, messages):
        self.calls += 1
        return {
            "committed": 1,
            "messages": [SystemMessage(content="[Collapsed Context]\nDRAINED")] + list(messages[-1:]),
        }


class _EscalationModel:
    def __init__(self):
        self.max_tokens_values = []
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def bind(self, **kwargs):
        self.max_tokens_values.append(kwargs.get("max_tokens"))
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("max_output_tokens")
        return AIMessage(content="after escalate")


class _EscalationThenRecoveryModel:
    def __init__(self):
        self.max_tokens_values = []
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def bind(self, **kwargs):
        self.max_tokens_values.append(kwargs.get("max_tokens"))
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls in (1, 2):
            raise RuntimeError("max_output_tokens")
        return AIMessage(content="after recovery")


class _ContextOverflowModel:
    def __init__(self):
        self.calls = 0
        self.max_tokens_values = []

    def bind_tools(self, tools):
        return self

    def bind(self, **kwargs):
        self.max_tokens_values.append(kwargs.get("max_tokens"))
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("input length and `max_tokens` exceed context limit: 188059 + 20000 > 200000")
        return AIMessage(content="after parsed overflow")


class _TransientAPIError(Exception):
    def __init__(self, status: int, message: str, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.headers = headers or {}


class _RetryOnceModel:
    def __init__(self, status: int, headers: dict[str, str] | None = None):
        self.calls = 0
        self.status = status
        self.headers = headers or {}

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            raise _TransientAPIError(self.status, f"transient {self.status}", self.headers)
        return AIMessage(content=f"after retry {self.status}")


class _TruncatedResponseModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.max_tokens_values = []

    def bind_tools(self, tools):
        return self

    def bind(self, **kwargs):
        self.max_tokens_values.append(kwargs.get("max_tokens"))
        return self

    async def ainvoke(self, messages):
        response = self.responses[self.calls]
        self.calls += 1
        return response


class _StreamingToolModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        self.calls += 1
        if self.calls == 1:
            yield AIMessageChunk(content="thinking")
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "echo", "args": '{"message":"hi"}', "id": "tc-1", "index": 0}],
            )
            await asyncio.sleep(0.05)
            yield AIMessageChunk(content="done")
            return
        yield AIMessageChunk(content="final answer")


class _SplitArgsStreamingToolModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        self.calls += 1
        if self.calls == 1:
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "Read", "args": "", "id": "tc-read", "index": 0}],
            )
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": None, "args": '{"file_path":"/tmp/a.txt"}', "id": "tc-read", "index": 0}],
            )
            await asyncio.sleep(0.01)
            yield AIMessageChunk(content="done")
            return
        yield AIMessageChunk(content="final answer")


class _SplitStringValueStreamingToolModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        self.calls += 1
        if self.calls == 1:
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "Read", "args": '{"file_path":"/', "id": "tc-read", "index": 0}],
            )
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": None, "args": 'tmp/a.txt"}', "id": "tc-read", "index": 0}],
            )
            await asyncio.sleep(0.01)
            yield AIMessageChunk(content="done")
            return
        yield AIMessageChunk(content="final answer")


class _TwoToolStreamingModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        self.calls += 1
        if self.calls == 1:
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "unsafe", "args": '{"message":"u"}', "id": "tc-unsafe", "index": 0}],
            )
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "safe", "args": '{"message":"s"}', "id": "tc-safe", "index": 1}],
            )
            await asyncio.sleep(0.05)
            yield AIMessageChunk(content="done")
            return
        yield AIMessageChunk(content="final answer")


class _FailingStreamingToolModel:
    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        yield AIMessageChunk(
            content="",
            tool_call_chunks=[{"name": "echo", "args": '{"message":"boom"}', "id": "tc-1", "index": 0}],
        )
        await asyncio.sleep(0.005)
        raise RuntimeError("stream exploded")


class _FailingQueuedStreamingToolModel:
    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        yield AIMessageChunk(
            content="",
            tool_call_chunks=[{"name": "unsafe", "args": '{"message":"u"}', "id": "tc-unsafe", "index": 0}],
        )
        yield AIMessageChunk(
            content="",
            tool_call_chunks=[{"name": "safe", "args": '{"message":"s"}', "id": "tc-safe", "index": 1}],
        )
        await asyncio.sleep(0.005)
        raise RuntimeError("stream exploded")


class _ToolThenFinalStreamingModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        self.calls += 1
        if self.calls == 1:
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "echo", "args": '{"message":"boom"}', "id": "tc-1", "index": 0}],
            )
            await asyncio.sleep(0.01)
            yield AIMessageChunk(content="tool turn")
            return
        yield AIMessageChunk(content="final answer")


class _UnsafeThenSafeGapStreamingModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        self.calls += 1
        if self.calls == 1:
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "unsafe", "args": '{"message":"u"}', "id": "tc-unsafe", "index": 0}],
            )
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "safe", "args": '{"message":"s"}', "id": "tc-safe", "index": 1}],
            )
            await asyncio.sleep(0.08)
            yield AIMessageChunk(content="done")
            return
        yield AIMessageChunk(content="final answer")


class _BashAndSafeStreamingModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        self.calls += 1
        if self.calls == 1:
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "bash", "args": '{"command":"boom"}', "id": "tc-bash", "index": 0}],
            )
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "safe", "args": '{"message":"s"}', "id": "tc-safe", "index": 1}],
            )
            await asyncio.sleep(0.05)
            yield AIMessageChunk(content="done")
            return
        yield AIMessageChunk(content="final answer")


class _ExplodingToolMiddleware:
    async def awrap_tool_call(self, request, handler):
        raise RuntimeError("middleware boom")


@pytest.mark.asyncio
async def test_query_loop_does_not_double_apply_compact_boundary_before_memory_middleware():
    capture = _CaptureToolContextMiddleware()
    memory = _SummaryBoundaryMiddleware(boundary_index=3)
    model = mock_model_with_tool_call(tool_name="echo", args={"message": "ctx"}, then_text="done")

    def echo_handler(message: str) -> str:
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "echo", "parameters": {}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=True,
    )
    history = [
        HumanMessage(content="h0"),
        AIMessage(content="a1"),
        HumanMessage(content="h2"),
        HumanMessage(content="call echo"),
    ]
    loop = make_loop(
        model,
        registry=make_registry(entry),
        middleware=[memory, capture],
        app_state=AppState(compact_boundary_index=3),
        runtime=SimpleNamespace(cost=0.0),
    )

    async for _ in loop.query({"messages": history}):
        pass

    assert capture.messages is not None
    assert len(capture.messages) == 2
    assert capture.messages[0].content == "summary"
    assert capture.messages[1].content == "call echo"


@pytest.mark.asyncio
async def test_query_loop_syncs_compact_boundary_index_from_memory_middleware():
    memory = _SummaryBoundaryMiddleware(boundary_index=3)
    model = mock_model_no_tools("done")
    app_state = AppState()
    loop = make_loop(
        model,
        middleware=[memory],
        app_state=app_state,
        runtime=SimpleNamespace(cost=0.0),
    )

    async for _ in loop.query({"messages": [{"role": "user", "content": "hello"}]}):
        pass

    assert app_state.compact_boundary_index == 3


@pytest.mark.asyncio
async def test_query_loop_syncs_tool_context_after_real_memory_compaction():
    capture = _CaptureToolContextMiddleware()
    summary_model = MagicMock()
    summary_model.bind.return_value = summary_model
    summary_model.ainvoke = AsyncMock(return_value=AIMessage(content="SUMMARY"))

    memory = MemoryMiddleware(
        context_limit=40,
        compaction_config=SimpleNamespace(reserve_tokens=0, keep_recent_tokens=10),
        compaction_threshold=0.1,
    )
    memory.set_model(summary_model)

    model = mock_model_with_tool_call(tool_name="echo", args={"message": "ctx"}, then_text="done")

    def echo_handler(message: str) -> str:
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "echo", "parameters": {}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=True,
    )

    history = [
        HumanMessage(content="A" * 80),
        AIMessage(content="B" * 80),
        HumanMessage(content="C" * 80),
        HumanMessage(content="call echo"),
    ]
    app_state = AppState()
    loop = make_loop(
        model,
        registry=make_registry(entry),
        middleware=[memory, capture],
        app_state=app_state,
        runtime=SimpleNamespace(cost=0.0),
    )

    async for _ in loop.query({"messages": history}):
        pass

    assert capture.messages is not None
    assert isinstance(capture.messages[0], SystemMessage)
    assert "Conversation Summary" in capture.messages[0].content
    assert capture.messages[-1].content == "call echo"
    assert app_state.compact_boundary_index > 0


@pytest.mark.asyncio
async def test_query_loop_syncs_compact_boundary_before_tool_execution():
    capture = _CaptureToolContextMiddleware()
    summary_model = MagicMock()
    summary_model.bind.return_value = summary_model
    summary_model.ainvoke = AsyncMock(return_value=AIMessage(content="SUMMARY"))

    memory = MemoryMiddleware(
        context_limit=40,
        compaction_config=SimpleNamespace(reserve_tokens=0, keep_recent_tokens=10),
        compaction_threshold=0.1,
    )
    memory.set_model(summary_model)

    model = mock_model_with_tool_call(tool_name="echo", args={"message": "ctx"}, then_text="done")

    def echo_handler(message: str) -> str:
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "echo", "parameters": {}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=True,
    )

    history = [
        HumanMessage(content="A" * 80),
        AIMessage(content="B" * 80),
        HumanMessage(content="C" * 80),
        HumanMessage(content="call echo"),
    ]
    app_state = AppState()
    loop = make_loop(
        model,
        registry=make_registry(entry),
        middleware=[memory, capture],
        app_state=app_state,
        runtime=SimpleNamespace(cost=0.0),
    )

    async for _ in loop.query({"messages": history}):
        pass

    assert capture.messages is not None
    assert capture.boundary == app_state.compact_boundary_index
    assert capture.boundary > 0


@pytest.mark.asyncio
async def test_query_loop_recovers_from_max_output_tokens_with_explicit_continuation():
    model = _EscalationThenRecoveryModel()
    app_state = AppState()
    loop = make_loop(model, app_state=app_state, runtime=SimpleNamespace(cost=0.0))

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "start"}]})

    assert result["reason"] == "completed"
    assert result["transition"].reason.value == "max_output_tokens_recovery"
    assert model.calls == 3
    assert model.max_tokens_values == [64000, 64000]
    assert any(
        getattr(msg, "content", "") == "Output token limit hit. Resume directly with no apology or recap."
        for msg in app_state.messages
    )


@pytest.mark.asyncio
async def test_query_loop_escalates_max_output_tokens_before_continuation_recovery():
    model = _EscalationModel()
    app_state = AppState()
    loop = make_loop(model, app_state=app_state, runtime=SimpleNamespace(cost=0.0))

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "start"}]})

    assert result["reason"] == "completed"
    assert result["transition"].reason.value == "max_output_tokens_escalate"
    assert model.max_tokens_values == [64000]


@pytest.mark.asyncio
async def test_query_loop_parses_context_overflow_error_into_targeted_max_tokens_override():
    model = _ContextOverflowModel()
    app_state = AppState()
    loop = make_loop(model, app_state=app_state, runtime=SimpleNamespace(cost=0.0))

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "start"}]})

    assert result["reason"] == "completed"
    assert result["messages"][-1].content == "after parsed overflow"
    assert model.max_tokens_values == [10941]


@pytest.mark.asyncio
async def test_query_loop_retries_once_after_529_capacity_error():
    model = _RetryOnceModel(529)
    app_state = AppState()
    loop = make_loop(model, app_state=app_state, runtime=SimpleNamespace(cost=0.0))

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "start"}]})

    assert result["reason"] == "completed"
    assert result["messages"][-1].content == "after retry 529"
    assert model.calls == 2


@pytest.mark.asyncio
async def test_query_loop_retries_once_after_429_rate_limit_error():
    model = _RetryOnceModel(429, headers={"retry-after": "0"})
    app_state = AppState()
    loop = make_loop(model, app_state=app_state, runtime=SimpleNamespace(cost=0.0))

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "start"}]})

    assert result["reason"] == "completed"
    assert result["messages"][-1].content == "after retry 429"
    assert model.calls == 2


@pytest.mark.asyncio
async def test_query_loop_detects_truncated_response_and_escalates_without_yielding_partial():
    model = _TruncatedResponseModel(
        [
            AIMessage(content="partial", response_metadata={"finish_reason": "length"}),
            AIMessage(content="after escalate"),
        ]
    )
    app_state = AppState()
    loop = make_loop(model, app_state=app_state, runtime=SimpleNamespace(cost=0.0))

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "start"}]})

    assert result["reason"] == "completed"
    assert result["transition"].reason.value == "max_output_tokens_escalate"
    assert [msg.content for msg in result["messages"]] == ["after escalate"]
    assert model.max_tokens_values == [64000]


@pytest.mark.asyncio
async def test_query_loop_recovers_from_truncated_response_with_withheld_message_pattern():
    model = _TruncatedResponseModel(
        [
            AIMessage(content="partial-1", response_metadata={"finish_reason": "length"}),
            AIMessage(content="partial-2", response_metadata={"stop_reason": "max_tokens"}),
            AIMessage(content="after recovery"),
        ]
    )
    app_state = AppState()
    loop = make_loop(model, app_state=app_state, runtime=SimpleNamespace(cost=0.0))

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "start"}]})

    assert result["reason"] == "completed"
    assert result["transition"].reason.value == "max_output_tokens_recovery"
    assert any(getattr(msg, "content", "") == "partial-2" for msg in app_state.messages)
    assert any(
        getattr(msg, "content", "") == "Output token limit hit. Resume directly with no apology or recap."
        for msg in app_state.messages
    )


@pytest.mark.asyncio
async def test_query_loop_surfaces_withheld_truncated_message_after_recovery_exhausts():
    model = _TruncatedResponseModel(
        [
            AIMessage(content="partial-1", response_metadata={"finish_reason": "length"}),
            AIMessage(content="partial-2", response_metadata={"finish_reason": "length"}),
            AIMessage(content="partial-3", response_metadata={"finish_reason": "length"}),
            AIMessage(content="partial-4", response_metadata={"finish_reason": "length"}),
            AIMessage(content="partial-5", response_metadata={"finish_reason": "length"}),
        ]
    )
    app_state = AppState()
    loop = make_loop(model, app_state=app_state, runtime=SimpleNamespace(cost=0.0))

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "start"}]})

    assert result["reason"] == "model_error"
    assert result["messages"][-1].content == "partial-5"


@pytest.mark.asyncio
async def test_query_loop_retries_prompt_too_long_via_reactive_compact():
    model = MagicMock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(
        side_effect=[
            RuntimeError("prompt is too long"),
            AIMessage(content="after compact"),
        ]
    )
    app_state = AppState()
    loop = make_loop(
        model,
        middleware=[_ReactiveCompactMiddleware()],
        app_state=app_state,
        runtime=SimpleNamespace(cost=0.0),
    )

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "start"}]})

    assert result["reason"] == "completed"
    assert result["transition"].reason.value == "reactive_compact_retry"
    assert model.ainvoke.call_count == 2
    assert isinstance(app_state.messages[0], SystemMessage)
    assert "Conversation Summary" in app_state.messages[0].content


@pytest.mark.asyncio
async def test_query_loop_retries_prompt_too_long_via_collapse_drain_before_compact():
    collapse = _CollapseDrainMiddleware()
    model = MagicMock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(
        side_effect=[
            RuntimeError("prompt is too long"),
            AIMessage(content="after drain"),
        ]
    )
    app_state = AppState()
    loop = make_loop(
        model,
        middleware=[collapse],
        app_state=app_state,
        runtime=SimpleNamespace(cost=0.0),
    )

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "start"}]})

    assert result["reason"] == "completed"
    assert result["transition"].reason.value == "collapse_drain_retry"
    assert collapse.calls == 1
    assert model.ainvoke.call_count == 2
    assert isinstance(app_state.messages[0], SystemMessage)
    assert "Collapsed Context" in app_state.messages[0].content


@pytest.mark.asyncio
async def test_query_loop_collapse_drain_is_single_shot_before_reactive_compact():
    collapse = _CollapseDrainMiddleware()
    model = MagicMock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(
        side_effect=[
            RuntimeError("prompt is too long"),
            RuntimeError("prompt is too long"),
            AIMessage(content="after compact"),
        ]
    )
    app_state = AppState()
    loop = make_loop(
        model,
        middleware=[collapse, _ReactiveCompactMiddleware()],
        app_state=app_state,
        runtime=SimpleNamespace(cost=0.0),
    )

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "start"}]})

    assert result["reason"] == "completed"
    assert result["transition"].reason.value == "reactive_compact_retry"
    assert collapse.calls == 1
    assert model.ainvoke.call_count == 3
    assert isinstance(app_state.messages[0], SystemMessage)
    assert "Conversation Summary" in app_state.messages[0].content


@pytest.mark.asyncio
async def test_query_loop_can_emit_tool_results_before_final_agent_message():
    model = _StreamingToolModel()

    async def echo_handler(message: str) -> str:
        await asyncio.sleep(0.01)
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "echo", "parameters": {}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(entry),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    event_order: list[str] = []
    async for chunk in loop.astream({"messages": [{"role": "user", "content": "call echo"}]}):
        if "tools" in chunk:
            event_order.append("tools")
        if "agent" in chunk:
            event_order.append("agent")

    assert "tools" in event_order
    assert "agent" in event_order
    assert event_order.index("tools") < event_order.index("agent")


@pytest.mark.asyncio
async def test_streaming_executor_blocks_safe_tool_behind_running_unsafe_tool():
    model = _TwoToolStreamingModel()
    starts: list[str] = []

    async def unsafe_handler(message: str) -> str:
        starts.append(f"start-unsafe-{message}")
        await asyncio.sleep(0.03)
        starts.append(f"end-unsafe-{message}")
        return f"unsafe: {message}"

    async def safe_handler(message: str) -> str:
        starts.append(f"start-safe-{message}")
        await asyncio.sleep(0.001)
        starts.append(f"end-safe-{message}")
        return f"safe: {message}"

    unsafe_entry = ToolEntry(
        name="unsafe",
        mode=ToolMode.INLINE,
        schema={"name": "unsafe", "description": "unsafe", "parameters": {}},
        handler=unsafe_handler,
        source="test",
        is_concurrency_safe=False,
    )
    safe_entry = ToolEntry(
        name="safe",
        mode=ToolMode.INLINE,
        schema={"name": "safe", "description": "safe", "parameters": {}},
        handler=safe_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(unsafe_entry, safe_entry),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    async for _ in loop.astream({"messages": [{"role": "user", "content": "call both"}]}):
        pass

    assert starts == [
        "start-unsafe-u",
        "end-unsafe-u",
        "start-safe-s",
        "end-safe-s",
    ]


@pytest.mark.asyncio
async def test_streaming_executor_discards_running_tasks_on_stream_failure():
    model = _FailingStreamingToolModel()
    events: list[str] = []

    async def echo_handler(message: str) -> str:
        events.append(f"start-{message}")
        try:
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            events.append(f"cancel-{message}")
            raise
        events.append(f"finish-{message}")
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "echo", "parameters": {}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(entry),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "call echo"}]})
    await asyncio.sleep(0.06)

    assert result["reason"] == "model_error"
    assert "start-boom" in events
    assert "cancel-boom" in events
    assert "finish-boom" not in events
    assert any("streaming discarded: streaming_error" in msg.content for msg in result["messages"])


@pytest.mark.asyncio
async def test_streaming_executor_discards_queued_tools_without_starting_them():
    model = _FailingQueuedStreamingToolModel()
    events: list[str] = []

    async def unsafe_handler(message: str) -> str:
        events.append(f"start-unsafe-{message}")
        try:
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            events.append(f"cancel-unsafe-{message}")
            raise
        events.append(f"finish-unsafe-{message}")
        return f"unsafe: {message}"

    async def safe_handler(message: str) -> str:
        events.append(f"start-safe-{message}")
        await asyncio.sleep(0.001)
        events.append(f"finish-safe-{message}")
        return f"safe: {message}"

    unsafe_entry = ToolEntry(
        name="unsafe",
        mode=ToolMode.INLINE,
        schema={"name": "unsafe", "description": "unsafe", "parameters": {}},
        handler=unsafe_handler,
        source="test",
        is_concurrency_safe=False,
    )
    safe_entry = ToolEntry(
        name="safe",
        mode=ToolMode.INLINE,
        schema={"name": "safe", "description": "safe", "parameters": {}},
        handler=safe_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(unsafe_entry, safe_entry),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "call both"}]})
    await asyncio.sleep(0.06)

    assert result["reason"] == "model_error"
    assert "start-unsafe-u" in events
    assert "cancel-unsafe-u" in events
    assert "finish-unsafe-u" not in events
    assert "start-safe-s" not in events
    tool_errors = [msg for msg in result["messages"] if isinstance(msg, ToolMessage)]
    assert {msg.tool_call_id for msg in tool_errors} == {"tc-unsafe", "tc-safe"}
    assert all("streaming discarded: streaming_error" in msg.content for msg in tool_errors)


@pytest.mark.asyncio
async def test_streaming_executor_uses_per_call_concurrency_safety():
    class _DynamicConcurrencyStreamingModel:
        def __init__(self):
            self.calls = 0

        def bind_tools(self, tools):
            return self

        async def astream(self, messages):
            self.calls += 1
            if self.calls == 1:
                yield AIMessageChunk(
                    content="",
                    tool_call_chunks=[{"name": "maybe_parallel", "args": '{"message":"u","parallel":false}', "id": "tc-maybe", "index": 0}],
                )
                yield AIMessageChunk(
                    content="",
                    tool_call_chunks=[{"name": "safe", "args": '{"message":"s"}', "id": "tc-safe", "index": 1}],
                )
                await asyncio.sleep(0.05)
                yield AIMessageChunk(content="done")
                return
            yield AIMessageChunk(content="final answer")

    model = _DynamicConcurrencyStreamingModel()
    starts: list[str] = []

    async def maybe_parallel_handler(message: str, parallel: bool) -> str:
        starts.append(f"start-maybe-{message}")
        await asyncio.sleep(0.02)
        starts.append(f"end-maybe-{message}")
        return f"maybe: {message}"

    async def safe_handler(message: str) -> str:
        starts.append(f"start-safe-{message}")
        await asyncio.sleep(0.001)
        starts.append(f"end-safe-{message}")
        return f"safe: {message}"

    maybe_entry = ToolEntry(
        name="maybe_parallel",
        mode=ToolMode.INLINE,
        schema={"name": "maybe_parallel", "description": "maybe", "parameters": {}},
        handler=maybe_parallel_handler,
        source="test",
        is_concurrency_safe=lambda parsed: bool(parsed.get("parallel")),
    )
    safe_entry = ToolEntry(
        name="safe",
        mode=ToolMode.INLINE,
        schema={"name": "safe", "description": "safe", "parameters": {}},
        handler=safe_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(maybe_entry, safe_entry),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    async for _ in loop.astream({"messages": [{"role": "user", "content": "call both"}]}):
        pass

    assert starts == [
        "start-maybe-u",
        "end-maybe-u",
        "start-safe-s",
        "end-safe-s",
    ]


@pytest.mark.asyncio
async def test_streaming_executor_missing_tool_completes_without_blocking_next_safe_tool():
    class _MissingThenSafeStreamingModel:
        def __init__(self):
            self.calls = 0

        def bind_tools(self, tools):
            return self

        async def astream(self, messages):
            self.calls += 1
            if self.calls == 1:
                yield AIMessageChunk(
                    content="",
                    tool_call_chunks=[{"name": "missing_tool", "args": '{}', "id": "tc-missing", "index": 0}],
                )
                yield AIMessageChunk(
                    content="",
                    tool_call_chunks=[{"name": "safe", "args": '{"message":"s"}', "id": "tc-safe", "index": 1}],
                )
                await asyncio.sleep(0.02)
                yield AIMessageChunk(content="done")
                return
            yield AIMessageChunk(content="final answer")

    model = _MissingThenSafeStreamingModel()
    starts: list[str] = []

    async def safe_handler(message: str) -> str:
        starts.append(f"start-safe-{message}")
        await asyncio.sleep(0.001)
        starts.append(f"end-safe-{message}")
        return f"safe: {message}"

    safe_entry = ToolEntry(
        name="safe",
        mode=ToolMode.INLINE,
        schema={"name": "safe", "description": "safe", "parameters": {}},
        handler=safe_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(safe_entry),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    pre_agent_tool_ids = []
    async for chunk in loop.astream({"messages": [{"role": "user", "content": "call missing then safe"}]}):
        if "tools" in chunk:
            pre_agent_tool_ids.extend(msg.tool_call_id for msg in chunk["tools"]["messages"])
        if "agent" in chunk:
            break

    assert pre_agent_tool_ids == ["tc-missing", "tc-safe"]
    assert starts == ["start-safe-s", "end-safe-s"]


@pytest.mark.asyncio
async def test_streaming_executor_missing_tool_is_immediately_completed():
    async def safe_handler(message: str) -> str:
        return f"safe:{message}"

    safe_entry = ToolEntry(
        name="safe",
        mode=ToolMode.INLINE,
        schema={"name": "safe", "description": "safe", "parameters": {}},
        handler=safe_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        mock_model_no_tools(),
        registry=make_registry(safe_entry),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )
    executor = _StreamingToolExecutor(loop=loop, tool_context=None)

    await executor.add_tool({"name": "missing_tool", "args": {}, "id": "tc-missing"})
    await executor.add_tool({"name": "safe", "args": {"message": "s"}, "id": "tc-safe"})

    assert [(tracked.tool_call.get("id"), tracked.status) for tracked in executor._tracked] == [
        ("tc-missing", "completed"),
        ("tc-safe", "executing"),
    ]
    assert executor._tracked[0].result is not None
    assert "Tool 'missing_tool' not found" in executor._tracked[0].result.content


@pytest.mark.asyncio
async def test_execute_tools_preserves_order_blocking_for_safe_after_unsafe():
    model = MagicMock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(
        side_effect=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "safe_a", "args": {"message": "a"}, "id": "tc-safe-a"},
                    {"name": "unsafe_b", "args": {"message": "b"}, "id": "tc-unsafe-b"},
                    {"name": "safe_c", "args": {"message": "c"}, "id": "tc-safe-c"},
                ],
            ),
            AIMessage(content="done"),
        ]
    )
    starts: list[str] = []

    async def safe_a_handler(message: str) -> str:
        starts.append(f"start-safe-a-{message}")
        await asyncio.sleep(0.001)
        starts.append(f"end-safe-a-{message}")
        return f"safe-a: {message}"

    async def unsafe_b_handler(message: str) -> str:
        starts.append(f"start-unsafe-b-{message}")
        await asyncio.sleep(0.02)
        starts.append(f"end-unsafe-b-{message}")
        return f"unsafe-b: {message}"

    async def safe_c_handler(message: str) -> str:
        starts.append(f"start-safe-c-{message}")
        await asyncio.sleep(0.001)
        starts.append(f"end-safe-c-{message}")
        return f"safe-c: {message}"

    loop = make_loop(
        model,
        registry=make_registry(
            ToolEntry(
                name="safe_a",
                mode=ToolMode.INLINE,
                schema={"name": "safe_a", "description": "safe_a", "parameters": {}},
                handler=safe_a_handler,
                source="test",
                is_concurrency_safe=True,
            ),
            ToolEntry(
                name="unsafe_b",
                mode=ToolMode.INLINE,
                schema={"name": "unsafe_b", "description": "unsafe_b", "parameters": {}},
                handler=unsafe_b_handler,
                source="test",
                is_concurrency_safe=False,
            ),
            ToolEntry(
                name="safe_c",
                mode=ToolMode.INLINE,
                schema={"name": "safe_c", "description": "safe_c", "parameters": {}},
                handler=safe_c_handler,
                source="test",
                is_concurrency_safe=True,
            ),
        ),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    async for _ in loop.astream({"messages": [{"role": "user", "content": "call ordered tools"}]}):
        pass

    assert starts == [
        "start-safe-a-a",
        "end-safe-a-a",
        "start-unsafe-b-b",
        "end-unsafe-b-b",
        "start-safe-c-c",
        "end-safe-c-c",
    ]


@pytest.mark.asyncio
async def test_streaming_executor_surfaces_middleware_exception_as_tool_error():
    model = _ToolThenFinalStreamingModel()

    async def echo_handler(message: str) -> str:
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "echo", "parameters": {}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(entry),
        middleware=[_ExplodingToolMiddleware()],
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "call echo"}]})

    assert result["reason"] == "completed"
    assert any(
        isinstance(msg, ToolMessage)
        and msg.tool_call_id == "tc-1"
        and "middleware boom" in msg.content
        for msg in result["messages"]
    )
    assert any(isinstance(msg, AIMessage) and msg.content == "final answer" for msg in result["messages"])


@pytest.mark.asyncio
async def test_streaming_executor_restarts_queue_after_unsafe_completion_before_final_chunk():
    model = _UnsafeThenSafeGapStreamingModel()
    starts: list[str] = []

    async def unsafe_handler(message: str) -> str:
        starts.append(f"start-unsafe-{message}")
        await asyncio.sleep(0.01)
        starts.append(f"end-unsafe-{message}")
        return f"unsafe: {message}"

    async def safe_handler(message: str) -> str:
        starts.append(f"start-safe-{message}")
        await asyncio.sleep(0.001)
        starts.append(f"end-safe-{message}")
        return f"safe: {message}"

    unsafe_entry = ToolEntry(
        name="unsafe",
        mode=ToolMode.INLINE,
        schema={"name": "unsafe", "description": "unsafe", "parameters": {}},
        handler=unsafe_handler,
        source="test",
        is_concurrency_safe=False,
    )
    safe_entry = ToolEntry(
        name="safe",
        mode=ToolMode.INLINE,
        schema={"name": "safe", "description": "safe", "parameters": {}},
        handler=safe_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(unsafe_entry, safe_entry),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    chunks = []
    async for chunk in loop.astream({"messages": [{"role": "user", "content": "call both"}]}):
        chunks.append(chunk)

    first_agent_index = next(i for i, chunk in enumerate(chunks) if "agent" in chunk)
    pre_agent_tool_ids = [
        msg.tool_call_id
        for chunk in chunks[:first_agent_index]
        for msg in chunk.get("tools", {}).get("messages", [])
    ]

    assert starts == [
        "start-unsafe-u",
        "end-unsafe-u",
        "start-safe-s",
        "end-safe-s",
    ]
    assert pre_agent_tool_ids == ["tc-unsafe", "tc-safe"]


@pytest.mark.asyncio
async def test_streaming_executor_bash_error_cancels_siblings_without_killing_parent():
    model = _BashAndSafeStreamingModel()
    events: list[str] = []

    async def bash_handler(command: str) -> str:
        events.append(f"start-bash-{command}")
        await asyncio.sleep(0.005)
        raise RuntimeError("bash exploded")

    async def safe_handler(message: str) -> str:
        events.append(f"start-safe-{message}")
        try:
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            events.append(f"cancel-safe-{message}")
            raise
        events.append(f"finish-safe-{message}")
        return f"safe: {message}"

    bash_entry = ToolEntry(
        name="bash",
        mode=ToolMode.INLINE,
        schema={"name": "bash", "description": "bash", "parameters": {}},
        handler=bash_handler,
        source="test",
        is_concurrency_safe=True,
    )
    safe_entry = ToolEntry(
        name="safe",
        mode=ToolMode.INLINE,
        schema={"name": "safe", "description": "safe", "parameters": {}},
        handler=safe_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(bash_entry, safe_entry),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "call bash and safe"}]})

    assert result["reason"] == "completed"
    assert "start-bash-boom" in events
    assert "start-safe-s" in events
    assert "cancel-safe-s" in events
    assert "finish-safe-s" not in events
    tool_messages = [msg for msg in result["messages"] if isinstance(msg, ToolMessage)]
    assert {msg.tool_call_id for msg in tool_messages} == {"tc-bash", "tc-safe"}
    assert any(msg.tool_call_id == "tc-bash" and "bash exploded" in msg.content for msg in tool_messages)
    assert any(msg.tool_call_id == "tc-safe" and "sibling" in msg.content for msg in tool_messages)


@pytest.mark.asyncio
async def test_query_loop_messages_updates_mode_forwards_live_stream_chunks():
    model = _StreamingToolModel()

    async def echo_handler(message: str) -> str:
        await asyncio.sleep(0.01)
        return f"echo: {message}"

    entry = ToolEntry(
        name="echo",
        mode=ToolMode.INLINE,
        schema={"name": "echo", "description": "echo", "parameters": {}},
        handler=echo_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(entry),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    events = []
    async for chunk in loop.astream(
        {"messages": [{"role": "user", "content": "call echo"}]},
        stream_mode=["messages", "updates"],
    ):
        events.append(chunk)

    message_events = [data for mode, data in events if mode == "messages"]
    texts = [msg.content for msg, _ in message_events if getattr(msg, "content", "")]
    tool_update_index = next(
        i for i, item in enumerate(events)
        if item[0] == "updates" and "tools" in item[1]
    )
    thinking_index = next(
        i for i, item in enumerate(events)
        if item[0] == "messages" and item[1][0].content == "thinking"
    )
    tool_chunk_index = next(
        i for i, item in enumerate(events)
        if item[0] == "messages"
        and getattr(item[1][0], "tool_call_chunks", None)
        and item[1][0].tool_call_chunks[0]["id"] == "tc-1"
    )

    assert thinking_index < tool_update_index
    assert tool_chunk_index < tool_update_index
    assert any(msg.content == "thinking" for msg, _ in message_events)
    assert any(
        getattr(msg, "tool_call_chunks", None)
        and msg.tool_call_chunks[0]["id"] == "tc-1"
        for msg, _ in message_events
    )
    assert texts == ["thinking", "done", "final answer"]


@pytest.mark.asyncio
async def test_streaming_overlap_waits_for_split_tool_call_args_before_execution():
    model = _SplitArgsStreamingToolModel()
    seen_args = []

    def read_handler(file_path: str) -> str:
        seen_args.append(file_path)
        return f"read:{file_path}"

    entry = ToolEntry(
        name="Read",
        mode=ToolMode.INLINE,
        schema={
            "name": "Read",
            "description": "read",
            "parameters": {
                "type": "object",
                "required": ["file_path"],
                "properties": {"file_path": {"type": "string"}},
            },
        },
        handler=read_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(entry),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "call read"}]})

    tool_messages = [msg for msg in result["messages"] if isinstance(msg, ToolMessage)]
    assert seen_args == ["/tmp/a.txt"]
    assert any(msg.tool_call_id == "tc-read" and msg.content == "read:/tmp/a.txt" for msg in tool_messages)
    assert not any("InputValidationError" in msg.content for msg in tool_messages)


@pytest.mark.asyncio
async def test_streaming_overlap_waits_for_split_string_value_before_execution():
    model = _SplitStringValueStreamingToolModel()
    seen_args = []

    def read_handler(file_path: str) -> str:
        seen_args.append(file_path)
        return f"read:{file_path}"

    entry = ToolEntry(
        name="Read",
        mode=ToolMode.INLINE,
        schema={
            "name": "Read",
            "description": "read",
            "parameters": {
                "type": "object",
                "required": ["file_path"],
                "properties": {"file_path": {"type": "string"}},
            },
        },
        handler=read_handler,
        source="test",
        is_concurrency_safe=True,
    )
    loop = make_loop(
        model,
        registry=make_registry(entry),
        app_state=AppState(),
        runtime=SimpleNamespace(cost=0.0),
    )

    result = await loop.ainvoke({"messages": [{"role": "user", "content": "call read"}]})

    tool_messages = [msg for msg in result["messages"] if isinstance(msg, ToolMessage)]
    assert seen_args == ["/tmp/a.txt"]
    assert any(msg.tool_call_id == "tc-read" and msg.content == "read:/tmp/a.txt" for msg in tool_messages)
    assert not any("InputValidationError" in msg.content for msg in tool_messages)
