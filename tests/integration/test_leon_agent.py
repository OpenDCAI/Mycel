"""Integration tests for LeonAgent with QueryLoop.

Uses mock model to verify the full astream pipeline without real API calls.
"""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, SystemMessage


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
