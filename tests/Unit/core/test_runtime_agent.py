from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.runtime.abort import AbortController
from core.runtime.agent import LeonAgent
from core.runtime.cleanup import CleanupRegistry
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


def test_close_uses_shutdown_fallback_for_model_client_cleanup(monkeypatch: pytest.MonkeyPatch):
    events: list[str] = []

    class _SyncClient:
        def close(self) -> None:
            events.append("sync")

    class _AsyncClient:
        async def aclose(self) -> None:
            events.append("async")

    async def _boom(_fn, *_args, **_kwargs):
        raise RuntimeError("cannot schedule new futures after interpreter shutdown")

    monkeypatch.setattr("core.runtime.agent.asyncio.to_thread", _boom)

    agent = object.__new__(LeonAgent)
    agent._session_started = False
    agent._session_ended = False
    agent._closing = False
    agent._closed = False
    agent._model_http_client = _SyncClient()
    agent._model_http_async_client = _AsyncClient()
    agent._cleanup_registry = CleanupRegistry()
    agent._cleanup_registry.register(agent._cleanup_model_clients, priority=1)

    LeonAgent.close(agent)

    assert events == ["async", "sync"]
    assert agent._closed is True
    assert agent._model_http_client is None
    assert agent._model_http_async_client is None


def test_close_logs_unexpected_runtimeerror_from_model_client_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    events: list[str] = []

    class _SyncClient:
        def close(self) -> None:
            events.append("sync")

    async def _boom(_fn, *_args, **_kwargs):
        raise RuntimeError("some other runtime problem")

    monkeypatch.setattr("core.runtime.agent.asyncio.to_thread", _boom)

    agent = object.__new__(LeonAgent)
    agent._session_started = False
    agent._session_ended = False
    agent._closing = False
    agent._closed = False
    agent._model_http_client = _SyncClient()
    agent._model_http_async_client = None
    agent._cleanup_registry = CleanupRegistry()
    agent._cleanup_registry.register(agent._cleanup_model_clients, priority=1)

    LeonAgent.close(agent)

    assert "some other runtime problem" in caplog.text
    assert events == []
    assert agent._closed is True


def test_close_remains_idempotent_after_shutdown_fallback(monkeypatch: pytest.MonkeyPatch):
    events: list[str] = []

    class _SyncClient:
        def close(self) -> None:
            events.append("sync")

    class _AsyncClient:
        async def aclose(self) -> None:
            events.append("async")

    async def _boom(_fn, *_args, **_kwargs):
        raise RuntimeError("cannot schedule new futures after interpreter shutdown")

    monkeypatch.setattr("core.runtime.agent.asyncio.to_thread", _boom)

    agent = object.__new__(LeonAgent)
    agent._session_started = False
    agent._session_ended = False
    agent._closing = False
    agent._closed = False
    agent._model_http_client = _SyncClient()
    agent._model_http_async_client = _AsyncClient()
    agent._cleanup_registry = CleanupRegistry()
    agent._cleanup_registry.register(agent._cleanup_model_clients, priority=1)

    LeonAgent.close(agent)
    LeonAgent.close(agent)

    assert events == ["async", "sync"]


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
