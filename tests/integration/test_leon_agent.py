"""Integration tests for LeonAgent with QueryLoop.

Uses mock model to verify the full astream pipeline without real API calls.
"""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage


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


def _empty_stream_model():
    class _EmptyStreamModel:
        def bind_tools(self, tools):
            return self

        def configurable_fields(self, **kwargs):
            return self

        def with_config(self, **kwargs):
            return self

        async def astream(self, messages):
            if False:
                yield AIMessageChunk(content="")

    return _EmptyStreamModel()


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


def test_leon_agent_destructor_does_not_reenable_skipped_sandbox_cleanup():
    """Explicit child close(cleanup_sandbox=False) must stay final under __del__."""
    from core.runtime.agent import LeonAgent

    agent = object.__new__(LeonAgent)
    agent._session_started = False
    agent._mark_terminated = MagicMock()
    agent._cleanup_mcp_client = MagicMock()
    agent._cleanup_sqlite_connection = MagicMock()
    agent._cleanup_sandbox = MagicMock()

    LeonAgent.close(agent, cleanup_sandbox=False)
    LeonAgent.__del__(agent)

    agent._cleanup_sandbox.assert_not_called()


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


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_astream_raises_loudly_on_empty_stream(tmp_path):
    """Empty streaming responses should surface as errors, not silent empty iterators."""
    from core.runtime.agent import LeonAgent

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=_empty_stream_model()), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        with pytest.raises(RuntimeError, match="streaming model returned no AIMessageChunk"):
            async for _ in agent.astream(
                "test",
                thread_id="test-empty-stream",
                stream_mode=["messages", "updates"],
            ):
                pass

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_memoizes_prompt_sections_between_builds(tmp_path):
    """Pattern 6: prompt sections should be cached across repeated prompt assembly."""
    from core.runtime.agent import LeonAgent
    from core.runtime import prompts as prompt_builders

    mock_model = _mock_model("Prompt cache response")
    original_context = prompt_builders.build_context_section
    original_rules = prompt_builders.build_rules_section
    counts = {"context": 0, "rules": 0}

    def counted_context(*args, **kwargs):
        counts["context"] += 1
        return original_context(*args, **kwargs)

    def counted_rules(*args, **kwargs):
        counts["rules"] += 1
        return original_rules(*args, **kwargs)

    with patch("core.runtime.prompts.build_context_section", side_effect=counted_context), \
         patch("core.runtime.prompts.build_rules_section", side_effect=counted_rules), \
         patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        first = agent._compose_system_prompt()
        second = agent._compose_system_prompt()

        assert first == second
        assert counts == {"context": 1, "rules": 1}

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_clear_thread_invalidates_prompt_section_cache(tmp_path):
    """Pattern 6: clear should invalidate cached prompt sections before rebuilding."""
    from core.runtime.agent import LeonAgent
    from core.runtime import prompts as prompt_builders

    mock_model = _mock_model("Prompt clear response")
    original_context = prompt_builders.build_context_section
    original_rules = prompt_builders.build_rules_section
    counts = {"context": 0, "rules": 0}

    def counted_context(*args, **kwargs):
        counts["context"] += 1
        return original_context(*args, **kwargs)

    def counted_rules(*args, **kwargs):
        counts["rules"] += 1
        return original_rules(*args, **kwargs)

    with patch("core.runtime.prompts.build_context_section", side_effect=counted_context), \
         patch("core.runtime.prompts.build_rules_section", side_effect=counted_rules), \
         patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()
        agent.agent.aclear = AsyncMock()

        assert counts == {"context": 1, "rules": 1}

        await agent.aclear_thread("prompt-clear-thread")

        assert counts == {"context": 2, "rules": 2}

        agent.close()


def test_build_rules_section_omits_tool_specific_usage_lore():
    from core.runtime.prompts import build_rules_section

    rules = build_rules_section(
        is_sandbox=False,
        working_dir="/repo",
        workspace_root="/repo",
    )

    assert "**Workspace**" in rules
    assert "**Absolute Paths**" in rules
    assert "**Security**" in rules
    assert "**Tool Priority**" in rules
    assert "Use Dedicated Tools Instead of Shell Commands" not in rules
    assert "Background Task Description" not in rules
    assert "**Deferred Tools**" not in rules


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_session_start_hook_runs_on_ainit(tmp_path):
    from core.runtime.agent import LeonAgent

    mock_model = _mock_model("Session start response")
    seen = []

    def on_start(payload):
        seen.append(payload)

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        agent.app_state.add_session_hook("SessionStart", on_start)

        await agent.ainit()

        assert len(seen) == 1
        assert seen[0]["event"] == "SessionStart"
        assert seen[0]["sandbox"] == "local"

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_session_end_hook_runs_on_close(tmp_path):
    from core.runtime.agent import LeonAgent

    mock_model = _mock_model("Session end response")
    seen = []

    def on_end(payload):
        seen.append(payload)

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()
        agent.app_state.add_session_hook("SessionEnd", on_end)

        agent.close()

        assert len(seen) == 1
        assert seen[0]["event"] == "SessionEnd"
        assert seen[0]["sandbox"] == "local"


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_session_hooks_support_async_callbacks_and_fire_once(tmp_path):
    from core.runtime.agent import LeonAgent

    mock_model = _mock_model("Session once response")
    seen = []

    async def on_start(payload):
        seen.append(("start", payload["event"]))

    async def on_end(payload):
        seen.append(("end", payload["event"]))

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        agent.app_state.add_session_hook("SessionStart", on_start)
        agent.app_state.add_session_hook("SessionEnd", on_end)

        await agent.ainit()
        await agent.ainit()
        agent.close()
        agent.close()

        assert seen == [("start", "SessionStart"), ("end", "SessionEnd")]


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


class _DeferredCrossThreadProbeModel:
    def __init__(self):
        self.turn_tool_names: list[list[str]] = []
        self._tools: list[dict] = []

    def bind_tools(self, tools):
        self._tools = list(tools or [])
        self.turn_tool_names.append([tool.get("name") for tool in self._tools if isinstance(tool, dict)])
        return self

    def configurable_fields(self, **kwargs):
        return self

    def with_config(self, *args, **kwargs):
        return self

    async def ainvoke(self, messages):
        joined = " ".join(str(getattr(msg, "content", "")) for msg in messages)
        current_tool_names = {tool.get("name") for tool in self._tools if isinstance(tool, dict)}

        if "discover task tools" in joined and "TaskCreate" not in current_tool_names:
            return AIMessage(
                content="",
                tool_calls=[{"name": "tool_search", "args": {"query": "select:TaskCreate"}, "id": "tc-search"}],
            )

        if "discover task tools" in joined:
            return AIMessage(content="discover-done")

        return AIMessage(content="plain-done")


class _DeferredResumeProbeModel:
    def __init__(self):
        self.turn_tool_names: list[list[str]] = []
        self._tools: list[dict] = []

    def bind_tools(self, tools):
        self._tools = list(tools or [])
        self.turn_tool_names.append([tool.get("name") for tool in self._tools if isinstance(tool, dict)])
        return self

    def configurable_fields(self, **kwargs):
        return self

    def with_config(self, *args, **kwargs):
        return self

    async def ainvoke(self, messages):
        return AIMessage(content="resume-done")


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
async def test_leon_agent_deferred_discovery_does_not_leak_across_threads(tmp_path):
    """Deferred tools discovered on one thread must not become inline on another thread."""
    from core.runtime.agent import LeonAgent

    probe_model = _DeferredCrossThreadProbeModel()

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=probe_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        result_a = await agent.ainvoke("discover task tools", thread_id="thread-A")
        result_b = await agent.ainvoke("plain request", thread_id="thread-B")

        assert result_a["reason"] == "completed"
        assert result_b["reason"] == "completed"
        assert len(probe_model.turn_tool_names) >= 3

        first_thread_a, second_thread_a, first_thread_b = probe_model.turn_tool_names[:3]
        assert "TaskCreate" not in first_thread_a
        assert "TaskCreate" in second_thread_a
        assert "TaskCreate" not in first_thread_b

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_restores_discovered_deferred_tools_after_restart(tmp_path):
    """Restarting the loop on the same thread should restore prior deferred discoveries from history."""
    from core.runtime.agent import LeonAgent

    checkpointer = _MemoryCheckpointer()
    discovery_model = _DeferredDiscoveryProbeModel()

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=discovery_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()
        agent.checkpointer = checkpointer
        agent.agent.checkpointer = checkpointer

        result = await agent.ainvoke("discover task tools", thread_id="resume-thread")
        assert result["reason"] == "completed"
        agent.close()

    resume_model = _DeferredResumeProbeModel()

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=resume_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()
        agent.checkpointer = checkpointer
        agent.agent.checkpointer = checkpointer

        result = await agent.ainvoke("after restart", thread_id="resume-thread")

        assert result["reason"] == "completed"
        assert resume_model.turn_tool_names
        assert "TaskCreate" in resume_model.turn_tool_names[0]

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


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_aclear_thread_does_not_restore_stale_summary(tmp_path):
    from core.runtime.agent import LeonAgent
    from core.runtime.middleware import ModelRequest, ModelResponse
    from core.runtime.middleware.memory.summary_store import SummaryStore
    from sandbox.thread_context import set_current_thread_id

    async def _handler(req: ModelRequest) -> ModelResponse:
        return ModelResponse(result=[AIMessage(content="final")], request_messages=req.messages)

    mock_model = _mock_model("clearable response")
    checkpointer = _MemoryCheckpointer()

    with patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model), \
         patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])), \
         patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None):

        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()
        agent.checkpointer = checkpointer
        agent.agent.checkpointer = checkpointer

        store = SummaryStore(tmp_path / "summary.db")
        agent._memory_middleware.summary_store = store
        store.save_summary(
            thread_id="clear-summary-thread",
            summary_text="STALE SUMMARY",
            compact_up_to_index=2,
            compacted_at=2,
        )

        await agent.aclear_thread("clear-summary-thread")

        assert store.get_latest_summary("clear-summary-thread") is None

        set_current_thread_id("clear-summary-thread")
        request = ModelRequest(
            model=mock_model,
            messages=[HumanMessage(content="fresh-1"), HumanMessage(content="fresh-2")],
            system_message=SystemMessage(content="sys"),
        )
        result = await agent._memory_middleware.awrap_model_call(request, _handler)

        assert [msg.content for msg in result.request_messages] == ["fresh-1", "fresh-2"]

        agent.close()
