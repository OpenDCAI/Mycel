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


def test_close_uses_direct_model_client_cleanup_during_shutdown(monkeypatch: pytest.MonkeyPatch):
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


def test_close_remains_idempotent_after_direct_shutdown_cleanup(monkeypatch: pytest.MonkeyPatch):
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


def test_dunder_del_swallows_interpreter_shutdown_runtimeerror(monkeypatch: pytest.MonkeyPatch):
    agent = object.__new__(LeonAgent)

    def _boom() -> None:
        raise RuntimeError("can't create new thread at interpreter shutdown")

    monkeypatch.setattr(agent, "close", _boom)

    LeonAgent.__del__(agent)


def test_dunder_del_swallows_executor_shutdown_runtimeerror(monkeypatch: pytest.MonkeyPatch):
    agent = object.__new__(LeonAgent)

    def _boom() -> None:
        raise RuntimeError("cannot schedule new futures after interpreter shutdown")

    monkeypatch.setattr(agent, "close", _boom)

    LeonAgent.__del__(agent)


def test_dunder_del_reraises_unrelated_runtimeerror(monkeypatch: pytest.MonkeyPatch):
    agent = object.__new__(LeonAgent)

    def _boom() -> None:
        raise RuntimeError("some other runtime problem")

    monkeypatch.setattr(agent, "close", _boom)

    with pytest.raises(RuntimeError, match="some other runtime problem"):
        LeonAgent.__del__(agent)


def test_dunder_del_calls_close_without_noise_when_close_succeeds(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    agent = object.__new__(LeonAgent)

    def _ok() -> None:
        calls.append("close")

    monkeypatch.setattr(agent, "close", _ok)

    LeonAgent.__del__(agent)

    assert calls == ["close"]


def test_dunder_del_reraises_non_runtime_errors(monkeypatch: pytest.MonkeyPatch):
    agent = object.__new__(LeonAgent)

    def _boom() -> None:
        raise ValueError("not a runtime error")

    monkeypatch.setattr(agent, "close", _boom)

    with pytest.raises(ValueError, match="not a runtime error"):
        LeonAgent.__del__(agent)


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


def test_build_middleware_stack_skips_prompt_caching_for_non_anthropic_provider(
    monkeypatch: pytest.MonkeyPatch,
):
    prompt_calls: list[str] = []
    mcp = object()
    steering = object()
    toolrunner = object()

    class _PromptCachingProbe:
        def __init__(self, **_kwargs) -> None:
            prompt_calls.append("prompt")

    class _MonitorProbe:
        def __init__(self, **_kwargs) -> None:
            self.runtime = SimpleNamespace()
            self._context_monitor = SimpleNamespace(context_limit=128000)

    monkeypatch.setattr("core.runtime.agent.PromptCachingMiddleware", _PromptCachingProbe)
    monkeypatch.setattr("core.runtime.agent.MonitorMiddleware", _MonitorProbe)
    monkeypatch.setattr("core.runtime.agent.McpInstructionsDeltaMiddleware", lambda **_kwargs: mcp)
    monkeypatch.setattr("core.runtime.agent.SteeringMiddleware", lambda **_kwargs: steering)
    monkeypatch.setattr("core.runtime.agent.ToolRunner", lambda **_kwargs: toolrunner)
    monkeypatch.setattr("core.runtime.agent.SpillBufferMiddleware", lambda **_kwargs: "spill")

    agent = object.__new__(LeonAgent)
    agent._sandbox = SimpleNamespace(fs=lambda: SimpleNamespace(), name="local", close=lambda: None)
    agent.config = SimpleNamespace(
        runtime=SimpleNamespace(context_limit=0),
        memory=SimpleNamespace(
            pruning=SimpleNamespace(enabled=False),
            compaction=SimpleNamespace(enabled=False),
        ),
        tools=SimpleNamespace(
            spill_buffer=SimpleNamespace(enabled=False),
        ),
    )
    agent._current_model_config = {"model_provider": "openai"}
    agent._model_overrides = {}
    agent.workspace_root = Path("/tmp")
    agent.queue_manager = SimpleNamespace()
    agent._tool_registry = SimpleNamespace()
    agent._get_mcp_instruction_blocks = lambda: []
    agent.model_name = "gpt-5.4"
    agent.verbose = False
    agent._closed = True
    agent._closing = False

    middleware = LeonAgent._build_middleware_stack(agent)

    assert prompt_calls == []
    assert middleware == [agent._monitor_middleware, mcp, steering, toolrunner]


def test_build_middleware_stack_keeps_prompt_caching_for_anthropic_provider(
    monkeypatch: pytest.MonkeyPatch,
):
    prompt_calls: list[str] = []
    mcp = object()
    steering = object()
    toolrunner = object()

    class _PromptCachingProbe:
        def __init__(self, **_kwargs) -> None:
            prompt_calls.append("prompt")

    class _MonitorProbe:
        def __init__(self, **_kwargs) -> None:
            self.runtime = SimpleNamespace()
            self._context_monitor = SimpleNamespace(context_limit=128000)

    monkeypatch.setattr("core.runtime.agent.PromptCachingMiddleware", _PromptCachingProbe)
    monkeypatch.setattr("core.runtime.agent.MonitorMiddleware", _MonitorProbe)
    monkeypatch.setattr("core.runtime.agent.McpInstructionsDeltaMiddleware", lambda **_kwargs: mcp)
    monkeypatch.setattr("core.runtime.agent.SteeringMiddleware", lambda **_kwargs: steering)
    monkeypatch.setattr("core.runtime.agent.ToolRunner", lambda **_kwargs: toolrunner)
    monkeypatch.setattr("core.runtime.agent.SpillBufferMiddleware", lambda **_kwargs: "spill")

    agent = object.__new__(LeonAgent)
    agent._sandbox = SimpleNamespace(fs=lambda: SimpleNamespace(), name="local", close=lambda: None)
    agent.config = SimpleNamespace(
        runtime=SimpleNamespace(context_limit=0),
        memory=SimpleNamespace(
            pruning=SimpleNamespace(enabled=False),
            compaction=SimpleNamespace(enabled=False),
        ),
        tools=SimpleNamespace(
            spill_buffer=SimpleNamespace(enabled=False),
        ),
    )
    agent._current_model_config = {"model_provider": "anthropic"}
    agent._model_overrides = {}
    agent.workspace_root = Path("/tmp")
    agent.queue_manager = SimpleNamespace()
    agent._tool_registry = SimpleNamespace()
    agent._get_mcp_instruction_blocks = lambda: []
    agent.model_name = "claude-sonnet"
    agent.verbose = False
    agent._closed = True
    agent._closing = False

    middleware = LeonAgent._build_middleware_stack(agent)

    assert prompt_calls == ["prompt"]
    assert len(middleware) == 5
    assert middleware[0] is agent._monitor_middleware
    assert middleware[2] is mcp
    assert middleware[3] is steering
    assert middleware[4] is toolrunner


def test_build_middleware_stack_skips_prompt_caching_when_provider_unknown(
    monkeypatch: pytest.MonkeyPatch,
):
    prompt_calls: list[str] = []
    mcp = object()
    steering = object()
    toolrunner = object()

    class _PromptCachingProbe:
        def __init__(self, **_kwargs) -> None:
            prompt_calls.append("prompt")

    class _MonitorProbe:
        def __init__(self, **_kwargs) -> None:
            self.runtime = SimpleNamespace()
            self._context_monitor = SimpleNamespace(context_limit=128000)

    monkeypatch.setattr("core.runtime.agent.PromptCachingMiddleware", _PromptCachingProbe)
    monkeypatch.setattr("core.runtime.agent.MonitorMiddleware", _MonitorProbe)
    monkeypatch.setattr("core.runtime.agent.McpInstructionsDeltaMiddleware", lambda **_kwargs: mcp)
    monkeypatch.setattr("core.runtime.agent.SteeringMiddleware", lambda **_kwargs: steering)
    monkeypatch.setattr("core.runtime.agent.ToolRunner", lambda **_kwargs: toolrunner)
    monkeypatch.setattr("core.runtime.agent.SpillBufferMiddleware", lambda **_kwargs: "spill")

    agent = object.__new__(LeonAgent)
    agent._sandbox = SimpleNamespace(fs=lambda: SimpleNamespace(), name="local", close=lambda: None)
    agent.config = SimpleNamespace(
        runtime=SimpleNamespace(context_limit=0),
        memory=SimpleNamespace(
            pruning=SimpleNamespace(enabled=False),
            compaction=SimpleNamespace(enabled=False),
        ),
        tools=SimpleNamespace(
            spill_buffer=SimpleNamespace(enabled=False),
        ),
    )
    agent._current_model_config = {"model_provider": None}
    agent._model_overrides = {}
    agent.workspace_root = Path("/tmp")
    agent.queue_manager = SimpleNamespace()
    agent._tool_registry = SimpleNamespace()
    agent._get_mcp_instruction_blocks = lambda: []
    agent.model_name = "gpt-5.4"
    agent.verbose = False
    agent._closed = True
    agent._closing = False

    middleware = LeonAgent._build_middleware_stack(agent)

    assert prompt_calls == []
    assert middleware == [agent._monitor_middleware, mcp, steering, toolrunner]
