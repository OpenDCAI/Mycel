from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.runtime.abort import AbortController
from core.runtime.agent import LeonAgent
from core.runtime.state import BootstrapConfig


def test_apply_forked_child_context_updates_agent_and_service_seams():
    agent = object.__new__(LeonAgent)
    agent.agent = SimpleNamespace(_bootstrap=None, _tool_abort_controller=None)
    agent._agent_service = SimpleNamespace(_parent_bootstrap=None, _parent_tool_context=None)

    bootstrap = BootstrapConfig(workspace_root=Path("/tmp"), model_name="test-model")
    tool_context = SimpleNamespace(abort_controller=AbortController())

    LeonAgent.apply_forked_child_context(agent, bootstrap, tool_context=tool_context)

    assert agent._bootstrap is bootstrap
    assert agent.agent._bootstrap is bootstrap
    assert agent._agent_service._parent_bootstrap is bootstrap
    assert agent._agent_service._parent_tool_context is tool_context
    assert agent.agent._tool_abort_controller is tool_context.abort_controller


def test_close_skips_sandbox_cleanup_and_stays_idempotent():
    agent = object.__new__(LeonAgent)
    agent._session_started = False
    agent._session_ended = False
    agent._closing = False
    agent._closed = False
    agent._cleanup_sandbox = MagicMock()
    agent._mark_terminated = MagicMock()
    agent._cleanup_mcp_client = MagicMock()

    LeonAgent.close(agent, cleanup_sandbox=False)
    LeonAgent.close(agent, cleanup_sandbox=True)

    agent._cleanup_sandbox.assert_not_called()
    agent._mark_terminated.assert_called_once()
    agent._cleanup_mcp_client.assert_called_once()


def test_memory_config_override_updates_compaction_trigger_without_losing_defaults():
    from config.schema import LeonSettings

    settings = LeonSettings()

    updated = LeonAgent._with_memory_config_override(
        settings,
        {"compaction": {"trigger_tokens": 80000}},
    )

    assert updated.memory.compaction.trigger_tokens == 80000
    assert updated.memory.compaction.reserve_tokens == settings.memory.compaction.reserve_tokens
    assert updated.memory.pruning.soft_trim_chars == settings.memory.pruning.soft_trim_chars
