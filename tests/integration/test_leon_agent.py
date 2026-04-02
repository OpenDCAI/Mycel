"""Integration tests for LeonAgent with QueryLoop.

Uses mock model to verify the full astream pipeline without real API calls.
"""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, SystemMessage, ToolMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_model(text="Integration test response"):
    """Create a mock LangChain model that returns a plain AIMessage."""
    ai_msg = AIMessage(content=text)
    model = MagicMock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(return_value=ai_msg)
    # configurable_fields support
    model.configurable_fields.return_value = model
    model.with_config.return_value = model
    return model


def _patch_env_api_key():
    """Ensure ANTHROPIC_API_KEY is set for LeonAgent init (uses a fake value)."""
    return patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-integration"})


class _MemoryCheckpointer:
    def __init__(self):
        self.store = {}

    async def aget(self, cfg):
        return self.store.get(cfg["configurable"]["thread_id"])

    async def aput(self, cfg, checkpoint, metadata, new_versions):
        self.store[cfg["configurable"]["thread_id"]] = checkpoint


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_simple_run(tmp_path):
    """LeonAgent with mock model: astream completes and yields chunks."""
    from core.runtime.agent import LeonAgent

    mock_model = _mock_model("Hello from integration test")

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        results = []
        async for chunk in agent.agent.astream(
            {"messages": [{"role": "user", "content": "hello"}]},
            config={"configurable": {"thread_id": "test-integration-1"}},
            stream_mode="updates",
        ):
            results.append(chunk)

        assert len(results) > 0
        # At least one agent chunk
        agent_chunks = [c for c in results if "agent" in c]
        assert len(agent_chunks) >= 1
        # Agent message content matches mock
        first_ai_msgs = agent_chunks[0]["agent"]["messages"]
        assert any("integration test" in str(m.content) for m in first_ai_msgs)

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_astream_interface_compatible(tmp_path):
    """astream yields dicts with 'agent' key — compatible with LangGraph stream_mode=updates."""
    from core.runtime.agent import LeonAgent

    mock_model = _mock_model("Compatible response")

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        chunks = []
        async for chunk in agent.agent.astream(
            {"messages": [{"role": "user", "content": "test"}]},
            config={"configurable": {"thread_id": "test-integration-2"}},
            stream_mode="updates",
        ):
            chunks.append(chunk)

        # All chunks are dicts
        assert all(isinstance(c, dict) for c in chunks)
        # All keys are one of "agent" or "tools"
        for c in chunks:
            assert set(c.keys()).issubset({"agent", "tools"})

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_astream_messages_updates_mode_yields_langgraph_tuples(tmp_path):
    """messages+updates mode must yield LangGraph-style (mode, data) tuples for SSE consumers."""
    from core.runtime.agent import LeonAgent

    mock_model = _mock_model("Tuple compatible response")

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        chunks = []
        async for chunk in agent.agent.astream(
            {"messages": [{"role": "user", "content": "tuple"}]},
            config={"configurable": {"thread_id": "test-integration-tuples"}},
            stream_mode=["messages", "updates"],
        ):
            chunks.append(chunk)

        assert chunks
        assert all(isinstance(chunk, tuple) and len(chunk) == 2 for chunk in chunks)
        assert any(mode == "messages" for mode, _ in chunks)
        assert any(mode == "updates" for mode, _ in chunks)

        message_chunks = [data for mode, data in chunks if mode == "messages"]
        first_msg_chunk, first_metadata = message_chunks[0]
        assert isinstance(first_msg_chunk, AIMessageChunk)
        assert "Tuple compatible response" in str(first_msg_chunk.content)
        assert isinstance(first_metadata, dict)

        update_chunks = [data for mode, data in chunks if mode == "updates"]
        assert any("agent" in update for update in update_chunks)

        agent.close()


class _DeferredDiscoveryProbeModel:
    def __init__(self):
        self.turn_tool_names: list[list[str]] = []
        self._tools: list[dict] = []
        self._turn = 0

    def bind_tools(self, tools):
        self._tools = list(tools or [])
        self.turn_tool_names.append([tool.get("name") for tool in self._tools if isinstance(tool, dict)])
        return self

    def configurable_fields(self, **kwargs):
        return self

    def with_config(self, *args, **kwargs):
        return self

    async def ainvoke(self, messages):
        if self._turn == 0:
            self._turn += 1
            return AIMessage(
                content="",
                tool_calls=[{"name": "tool_search", "args": {"query": "select:TaskCreate"}, "id": "tc-search"}],
            )
        self._turn += 1
        return AIMessage(content="done")


class _DeferredExecutionProbeModel:
    def __init__(self):
        self.turn_tool_names: list[list[str]] = []
        self._tools: list[dict] = []
        self._turn = 0

    def bind_tools(self, tools):
        self._tools = list(tools or [])
        self.turn_tool_names.append([tool.get("name") for tool in self._tools if isinstance(tool, dict)])
        return self

    def configurable_fields(self, **kwargs):
        return self

    def with_config(self, *args, **kwargs):
        return self

    async def ainvoke(self, messages):
        if self._turn == 0:
            self._turn += 1
            return AIMessage(
                content="",
                tool_calls=[{"name": "tool_search", "args": {"query": "select:TaskCreate"}, "id": "tc-search"}],
            )
        if self._turn == 1:
            self._turn += 1
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "TaskCreate",
                        "args": {"subject": "PT02_EXEC", "description": "created after discovery"},
                        "id": "tc-task-create",
                    }
                ],
            )
        self._turn += 1
        return AIMessage(content="PT02_EXEC_DONE")


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_reinjects_discovered_deferred_tool_schemas_on_following_turn(tmp_path):
    """Deferred tools discovered via tool_search must become real schemas on the next turn."""
    from core.runtime.agent import LeonAgent

    probe_model = _DeferredDiscoveryProbeModel()

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=probe_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        result = await agent.ainvoke("discover task tools", thread_id="test-deferred-discovery")

        assert result["reason"] == "completed"
        assert len(probe_model.turn_tool_names) >= 2
        first_turn, second_turn = probe_model.turn_tool_names[:2]
        assert "TaskCreate" not in first_turn
        assert "tool_search" in first_turn
        assert "TaskCreate" in second_turn

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_can_execute_discovered_deferred_tool_on_following_turn(tmp_path):
    """A deferred tool discovered via tool_search should become callable on the next turn."""
    from core.runtime.agent import LeonAgent

    probe_model = _DeferredExecutionProbeModel()

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=probe_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        result = await agent.ainvoke("discover then run deferred task tool", thread_id="test-deferred-execution")

        assert result["reason"] == "completed"
        assert len(probe_model.turn_tool_names) >= 2
        assert "TaskCreate" not in probe_model.turn_tool_names[0]
        assert "TaskCreate" in probe_model.turn_tool_names[1]

        task_tool_messages = [
            msg for msg in result["messages"]
            if isinstance(msg, ToolMessage) and msg.tool_call_id == "tc-task-create"
        ]
        assert len(task_tool_messages) == 1
        assert "PT02_EXEC" in str(task_tool_messages[0].content)
        assert any(isinstance(msg, AIMessage) and msg.content == "PT02_EXEC_DONE" for msg in result["messages"])

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_multiple_thread_ids(tmp_path):
    """Different thread_ids produce independent sessions (no cross-contamination)."""
    from core.runtime.agent import LeonAgent

    responses = iter(["Response for thread-A", "Response for thread-B"])
    mock_model = MagicMock()
    mock_model.bind_tools.return_value = mock_model
    mock_model.with_config.return_value = mock_model
    mock_model.configurable_fields.return_value = mock_model
    mock_model.ainvoke = AsyncMock(side_effect=[
        AIMessage(content="Response for thread-A"),
        AIMessage(content="Response for thread-B"),
    ])

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        chunks_a = []
        async for chunk in agent.agent.astream(
            {"messages": [{"role": "user", "content": "hi A"}]},
            config={"configurable": {"thread_id": "thread-A"}},
            stream_mode="updates",
        ):
            chunks_a.append(chunk)

        chunks_b = []
        async for chunk in agent.agent.astream(
            {"messages": [{"role": "user", "content": "hi B"}]},
            config={"configurable": {"thread_id": "thread-B"}},
            stream_mode="updates",
        ):
            chunks_b.append(chunk)

        # Both sessions produced chunks
        assert len(chunks_a) > 0
        assert len(chunks_b) > 0

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_astream_wrapper_exposes_caller_surface(tmp_path):
    """LeonAgent should expose a caller-owned astream surface instead of forcing callers onto agent.agent.astream."""
    from core.runtime.agent import LeonAgent

    mock_model = _mock_model("Caller surface response")

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        chunks = []
        async for chunk in agent.astream(
            "caller stream",
            thread_id="test-astream-wrapper",
            stream_mode=["messages", "updates"],
        ):
            chunks.append(chunk)

        assert chunks
        assert all(isinstance(chunk, tuple) and len(chunk) == 2 for chunk in chunks)

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_astream_can_enforce_max_budget_per_event(tmp_path):
    """Caller-owned astream surface should be able to stop once runtime cost exceeds a caller budget."""
    from core.runtime.agent import LeonAgent

    mock_model = _mock_model("Caller surface response")

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        async def fake_stream(*args, **kwargs):
            yield ("messages", ("first", {"langgraph_node": "agent"}))
            yield ("updates", {"agent": {"messages": [AIMessage(content="done")]}})

        agent.agent.astream = fake_stream
        agent.runtime = SimpleNamespace(cost=0.75)

        chunks = []
        with pytest.raises(RuntimeError, match="max_budget_usd exceeded"):
            async for chunk in agent.astream(
                "caller stream",
                thread_id="test-astream-budget",
                stream_mode=["messages", "updates"],
                max_budget_usd=0.5,
            ):
                chunks.append(chunk)

        assert chunks == [("messages", ("first", {"langgraph_node": "agent"}))]

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_aclear_thread_resets_thread_history(tmp_path):
    """aclear_thread should clear replayable thread history while preserving accumulators."""
    from core.runtime.agent import LeonAgent

    mock_model = _mock_model("clearable response")
    checkpointer = _MemoryCheckpointer()

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()
        agent.checkpointer = checkpointer
        agent.agent.checkpointer = checkpointer
        agent.app_state.total_cost = 1.25

        await agent.ainvoke("hello", thread_id="clear-agent-thread")
        assert checkpointer.store["clear-agent-thread"]["channel_values"]["messages"]

        agent.agent._tool_read_file_state["/tmp/file.py"] = {"partial": False}
        agent.agent._tool_loaded_nested_memory_paths.add("/tmp/memory.md")
        agent.agent._tool_discovered_skill_names.add("skill-a")
        old_session_id = agent._bootstrap.session_id

        await agent.aclear_thread("clear-agent-thread")

        assert checkpointer.store["clear-agent-thread"]["channel_values"]["messages"] == []
        assert agent.app_state.messages == []
        assert agent.app_state.turn_count == 0
        assert agent.app_state.compact_boundary_index == 0
        assert agent.app_state.total_cost == 1.25
        assert agent._bootstrap.session_id != old_session_id
        assert agent._bootstrap.parent_session_id == old_session_id

        agent.close()
