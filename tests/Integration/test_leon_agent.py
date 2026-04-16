"""Integration tests for LeonAgent with QueryLoop.

Uses mock model to verify the full astream pipeline without real API calls.
"""

import json
import os
from types import SimpleNamespace
from typing import Any, cast
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


class _FakeToolTaskRepo:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, dict[str, Any]]] = {}

    def close(self) -> None:
        return None

    def next_id(self, thread_id: str) -> str:
        tasks = self._rows.get(thread_id, {})
        if not tasks:
            return "1"
        return str(max(int(task_id) for task_id in tasks) + 1)

    def get(self, thread_id: str, task_id: str) -> dict[str, Any] | None:
        return self._rows.get(thread_id, {}).get(task_id)

    def list_all(self, thread_id: str) -> list[dict[str, Any]]:
        return list(self._rows.get(thread_id, {}).values())

    def insert(self, thread_id: str, task: Any) -> None:
        self._rows.setdefault(thread_id, {})[str(task.id)] = {"id": task.id, "task": task}

    def update(self, thread_id: str, task: Any) -> None:
        self._rows.setdefault(thread_id, {})[str(task.id)] = {"id": task.id, "task": task}

    def delete(self, thread_id: str, task_id: str) -> None:
        self._rows.get(thread_id, {}).pop(str(task_id), None)


class _FakeAgentRegistryRepo:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[str, str, str, str, str | None, str | None]] = {}

    def close(self) -> None:
        return None

    def register(
        self,
        *,
        agent_id: str,
        name: str,
        thread_id: str,
        status: str,
        parent_agent_id: str | None,
        subagent_type: str | None,
    ) -> None:
        self._rows[agent_id] = (agent_id, name, thread_id, status, parent_agent_id, subagent_type)

    def list_running_by_name(self, name: str) -> list[tuple[str, str, str, str, str | None, str | None]]:
        return [row for row in self._rows.values() if row[1] == name and row[3] == "running"]

    def remove(self, agent_id: str) -> None:
        self._rows.pop(agent_id, None)


class _FakeSyncFileRepo:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, tuple[str, int]]] = {}

    def close(self) -> None:
        return None

    def track_file(self, thread_id: str, relative_path: str, checksum: str, timestamp: int) -> None:
        self._rows.setdefault(thread_id, {})[relative_path] = (checksum, timestamp)

    def track_files_batch(self, thread_id: str, file_records: list[tuple[str, str, int]]) -> None:
        for relative_path, checksum, timestamp in file_records:
            self.track_file(thread_id, relative_path, checksum, timestamp)

    def get_file_info(self, thread_id: str, relative_path: str) -> dict[str, Any] | None:
        info = self._rows.get(thread_id, {}).get(relative_path)
        if info is None:
            return None
        return {"checksum": info[0], "last_synced": info[1]}

    def get_all_files(self, thread_id: str) -> dict[str, str]:
        return {path: checksum for path, (checksum, _timestamp) in self._rows.get(thread_id, {}).items()}

    def clear_thread(self, thread_id: str) -> int:
        removed = len(self._rows.get(thread_id, {}))
        self._rows.pop(thread_id, None)
        return removed


class _FakeSummaryRepo:
    def ensure_tables(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakeControlPlaneRepo:
    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _patch_runtime_storage_container(monkeypatch: pytest.MonkeyPatch):
    class _FakeRuntimeContainer:
        def __init__(self) -> None:
            self._tool_task_repo = _FakeToolTaskRepo()
            self._agent_registry_repo = _FakeAgentRegistryRepo()
            self._sync_file_repo = _FakeSyncFileRepo()
            self._queue_repo = object()
            self._summary_repo = _FakeSummaryRepo()
            self._terminal_repo = _FakeControlPlaneRepo()
            self._lease_repo = _FakeControlPlaneRepo()
            self._chat_session_repo = _FakeControlPlaneRepo()

        def tool_task_repo(self) -> _FakeToolTaskRepo:
            return self._tool_task_repo

        def agent_registry_repo(self) -> _FakeAgentRegistryRepo:
            return self._agent_registry_repo

        def sync_file_repo(self) -> _FakeSyncFileRepo:
            return self._sync_file_repo

        def queue_repo(self) -> object:
            return self._queue_repo

        def summary_repo(self) -> object:
            return self._summary_repo

        def terminal_repo(self) -> _FakeControlPlaneRepo:
            return self._terminal_repo

        def lease_repo(self) -> _FakeControlPlaneRepo:
            return self._lease_repo

        def chat_session_repo(self) -> _FakeControlPlaneRepo:
            return self._chat_session_repo

    container = _FakeRuntimeContainer()
    monkeypatch.setattr("storage.runtime.build_storage_container", lambda **_kwargs: container)
    return container


class _MemoryCheckpointer:
    def __init__(self):
        self.store = {}

    async def aget(self, cfg):
        return self.store.get(cfg["configurable"]["thread_id"])

    async def aput(self, cfg, checkpoint, metadata, new_versions):
        self.store[cfg["configurable"]["thread_id"]] = checkpoint


def _set_agent_checkpointer(agent: object, checkpointer: object) -> None:
    setattr(agent, "checkpointer", checkpointer)
    setattr(getattr(agent, "agent"), "checkpointer", checkpointer)


def _set_agent_runtime(agent: object, runtime: object) -> None:
    setattr(agent, "runtime", runtime)


def _require_tool_name(tool: dict[str, Any]) -> str:
    name = tool.get("name")
    assert isinstance(name, str)
    return name


class _DirectCompactionProbeModel:
    def __init__(self):
        self.summary_calls = 0
        self.turn_calls = 0

    def bind_tools(self, tools):
        return self

    def configurable_fields(self, **kwargs):
        return self

    def with_config(self, **kwargs):
        return self

    def bind(self, **kwargs):
        return self

    async def ainvoke(self, messages):
        first_content = getattr(messages[0], "content", "") if messages else ""
        if isinstance(first_content, str) and "summarizing conversations" in first_content:
            self.summary_calls += 1
            return AIMessage(
                content=(
                    "1. Request/Intent — summarize\n"
                    "2. Technical Concepts — compaction\n"
                    "3. Files/Code — none\n"
                    "4. Errors — none\n"
                    "5. Problem Solving — keep going\n"
                    "6. User Messages — large payloads\n"
                    "7. Pending Tasks — continue\n"
                    "8. Current Work — compacting\n"
                    "9. Next Step — answer user"
                )
            )

        self.turn_calls += 1
        return AIMessage(content=f"OK_{self.turn_calls}")


class _MessageCaptureModel:
    def __init__(self, text: str = "captured"):
        self.calls: list[list[object]] = []
        self.text = text

    def bind_tools(self, tools):
        return self

    def configurable_fields(self, **kwargs):
        return self

    def with_config(self, **kwargs):
        return self

    def bind(self, **kwargs):
        return self

    async def ainvoke(self, messages):
        self.calls.append(list(messages))
        return AIMessage(content=self.text)


def test_leon_agent_destructor_does_not_reenable_skipped_sandbox_cleanup():
    """Explicit child close(cleanup_sandbox=False) must stay final under __del__."""
    from core.runtime.agent import LeonAgent

    agent = object.__new__(LeonAgent)
    agent._session_started = False
    agent._mark_terminated = MagicMock()
    agent._cleanup_mcp_client = MagicMock()
    agent._cleanup_sandbox = MagicMock()

    LeonAgent.close(agent, cleanup_sandbox=False)
    LeonAgent.__del__(agent)

    agent._cleanup_sandbox.assert_not_called()


@_patch_env_api_key()
def test_create_leon_agent_supabase_defaults_wire_runtime_container(monkeypatch, tmp_path, _patch_runtime_storage_container):
    from core.runtime.agent import create_leon_agent

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=_mock_model("queue wiring")),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
    ):
        agent = create_leon_agent(workspace_root=str(tmp_path))

    try:
        assert agent.storage_container is _patch_runtime_storage_container
        assert agent.queue_manager._repo is _patch_runtime_storage_container.queue_repo()
        assert agent._memory_middleware.summary_store is not None
        assert agent._memory_middleware.summary_store._repo is _patch_runtime_storage_container.summary_repo()
    finally:
        agent.close()


@_patch_env_api_key()
def test_create_leon_agent_defaults_wire_runtime_container_when_strategy_missing(monkeypatch, tmp_path, _patch_runtime_storage_container):
    from core.runtime.agent import create_leon_agent

    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=_mock_model("queue wiring")),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
    ):
        agent = create_leon_agent(workspace_root=str(tmp_path))

    try:
        assert agent.storage_container is _patch_runtime_storage_container
        assert agent.queue_manager._repo is _patch_runtime_storage_container.queue_repo()
        assert agent._memory_middleware.summary_store is not None
        assert agent._memory_middleware.summary_store._repo is _patch_runtime_storage_container.summary_repo()
    finally:
        agent.close()


@_patch_env_api_key()
def test_create_leon_agent_defaults_to_process_local_agent_registry(monkeypatch, tmp_path, _patch_runtime_storage_container):
    from core.runtime.agent import LeonAgent

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    captured: dict[str, Any] = {}

    class _CapturingAgentService:
        def __init__(self, *args, **kwargs) -> None:
            captured.update(kwargs)
            self._agent_registry = None

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=_mock_model("registry wiring")),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.AgentService", _CapturingAgentService),
    ):
        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")

    try:
        assert agent._agent_registry is None
        assert agent._agent_service._agent_registry is None
        assert "agent_registry" not in captured
    finally:
        agent.close()


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_simple_run(monkeypatch, tmp_path):
    """LeonAgent with mock model: astream completes and yields chunks."""
    from core.runtime.agent import LeonAgent

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "sqlite")
    mock_model = _mock_model("Hello from integration test")

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
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
async def test_leon_agent_ainit_pushes_late_checkpointer_into_memory_middleware(tmp_path):
    """Async checkpointer init should update both QueryLoop and MemoryMiddleware."""
    from core.runtime.agent import LeonAgent

    mock_model = _mock_model("late checkpointer")
    checkpointer = _MemoryCheckpointer()

    async def _late_init_checkpointer(self):
        self.checkpointer = checkpointer

    with (
        patch.dict(
            os.environ,
            {
                "SUPABASE_PUBLIC_URL": "http://127.0.0.1:54320",
                "SUPABASE_INTERNAL_URL": "http://127.0.0.1:54320",
                "LEON_SUPABASE_SERVICE_ROLE_KEY": "dummy",
                "SUPABASE_ANON_KEY": "dummy",
            },
        ),
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new=_late_init_checkpointer),
        patch("core.runtime.agent.LeonAgent._init_mcp_tools", new_callable=AsyncMock, return_value=[]),
    ):
        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        assert agent._memory_middleware.checkpointer is None

        await agent.ainit()

        assert agent.agent.checkpointer is checkpointer
        assert agent._memory_middleware.checkpointer is checkpointer

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_astream_interface_compatible(tmp_path):
    """astream yields dicts with 'agent' key — compatible with LangGraph stream_mode=updates."""
    from core.runtime.agent import LeonAgent

    mock_model = _mock_model("Compatible response")

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
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

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
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

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=_empty_stream_model()),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
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
async def test_leon_agent_bundle_dir_registers_mcp_resource_tools(tmp_path):
    """Agent bundle MCP config should surface MCP resource tools in the live registry."""
    from core.runtime.agent import LeonAgent

    bundle_dir = tmp_path / "agent-bundles" / "toad"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "agent.md").write_text(
        "---\nname: Toad\ndescription: Demo agent\n---\nYou are Toad.\n",
        encoding="utf-8",
    )
    (bundle_dir / ".mcp.json").write_text(
        '{"mcpServers":{"nu50demo":{"transport":"stdio","command":"uv","args":["run","python","/tmp/nu50_mcp_server.py"]}}}',
        encoding="utf-8",
    )

    mock_model = _mock_model("Bundle MCP response")

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(
            workspace_root=str(tmp_path),
            bundle_dir=str(bundle_dir),
            api_key="sk-test-integration",
        )
        await agent.ainit()

        assert agent._tool_registry.get("ListMcpResources") is not None
        assert agent._tool_registry.get("ReadMcpResource") is not None

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_agent_config_id_registers_mcp_resource_tools(tmp_path):
    """Repo-rooted agent config should surface MCP resource tools in the live registry."""
    from core.runtime.agent import LeonAgent

    class _Repo:
        def get_config(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return {
                "id": "cfg-1",
                "name": "Toad",
                "description": "Demo agent",
                "tools": ["*"],
                "system_prompt": "You are Toad.",
                "status": "active",
                "version": "1.0.0",
                "runtime": {},
                "mcp": {
                    "nu50demo": {
                        "transport": "stdio",
                        "command": "uv",
                        "args": ["run", "python", "/tmp/nu50_mcp_server.py"],
                    }
                },
            }

        def list_rules(self, _agent_config_id: str):
            return []

        def list_sub_agents(self, _agent_config_id: str):
            return []

        def list_skills(self, _agent_config_id: str):
            return []

    mock_model = _mock_model("Repo MCP response")

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(
            workspace_root=str(tmp_path),
            agent_config_id="cfg-1",
            agent_config_repo=_Repo(),
            api_key="sk-test-integration",
        )
        await agent.ainit()

        assert agent._tool_registry.get("ListMcpResources") is not None
        assert agent._tool_registry.get("ReadMcpResource") is not None

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_agent_config_id_ignores_conflicting_stale_member_shell(tmp_path):
    """Repo-rooted live startup must ignore a stale member-dir shell with conflicting MCP state."""
    from core.runtime.agent import LeonAgent

    stale_member_dir = tmp_path / "members" / "toad"
    stale_member_dir.mkdir(parents=True)
    (stale_member_dir / "agent.md").write_text(
        "---\nname: Stale Toad\ndescription: Stale member shell\n---\nYou are Stale Toad.\n",
        encoding="utf-8",
    )
    (stale_member_dir / ".mcp.json").write_text('{"mcpServers":{}}', encoding="utf-8")

    class _Repo:
        def get_config(self, agent_config_id: str):
            assert agent_config_id == "cfg-1"
            return {
                "id": "cfg-1",
                "name": "Repo Toad",
                "description": "Repo-backed agent",
                "tools": ["*"],
                "system_prompt": "You are Repo Toad.",
                "status": "active",
                "version": "1.0.0",
                "runtime": {},
                "mcp": {
                    "nu50demo": {
                        "transport": "stdio",
                        "command": "uv",
                        "args": ["run", "python", "/tmp/nu50_mcp_server.py"],
                    }
                },
            }

        def list_rules(self, _agent_config_id: str):
            return []

        def list_sub_agents(self, _agent_config_id: str):
            return []

        def list_skills(self, _agent_config_id: str):
            return []

    mock_model = _mock_model("Repo MCP response")

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(
            workspace_root=str(tmp_path),
            agent_config_id="cfg-1",
            agent_config_repo=_Repo(),
            api_key="sk-test-integration",
        )
        await agent.ainit()

        # @@@runtime-repo-source-of-truth - repo-backed live startup must ignore
        # conflicting stale member shells and keep MCP registration sourced from agent_config_repo.
        assert "Repo Toad" in agent.system_prompt
        assert "Stale Toad" not in agent.system_prompt
        assert agent._tool_registry.get("ListMcpResources") is not None
        assert agent._tool_registry.get("ReadMcpResource") is not None

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_announces_mcp_instruction_delta_once_and_reannounces_on_change(tmp_path):
    from core.runtime.agent import LeonAgent

    bundle_dir = tmp_path / "agent-bundles" / "toad"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "agent.md").write_text(
        "---\nname: Toad\ndescription: Demo agent\n---\nYou are Toad.\n",
        encoding="utf-8",
    )

    def _write_mcp(instructions: str) -> None:
        (bundle_dir / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "nu50demo": {
                            "transport": "stdio",
                            "command": "uv",
                            "args": ["run", "python", "/tmp/nu50_mcp_server.py"],
                            "instructions": instructions,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

    def _message_text(message: object) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
        return str(content)

    def _delta_messages(messages: list[object]) -> list[str]:
        hits: list[str] = []
        for message in messages:
            content = _message_text(message)
            if "<mcp_instructions_delta>" in content:
                hits.append(content)
        return hits

    _write_mcp("Use nu50demo carefully.")
    first_model = _MessageCaptureModel("First MCP delta response")
    checkpointer = _MemoryCheckpointer()

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=first_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(
            workspace_root=str(tmp_path),
            bundle_dir=str(bundle_dir),
            api_key="sk-test-integration",
        )
        await agent.ainit()
        _set_agent_checkpointer(agent, checkpointer)

        await agent.ainvoke("first turn", thread_id="mcp-delta-thread")
        assert first_model.calls
        first_messages = first_model.calls[0]
        first_deltas = _delta_messages(first_messages)
        assert len(first_deltas) == 1
        assert "Use nu50demo carefully." in first_deltas[0]

        second_call_index = len(first_model.calls)
        await agent.ainvoke("second turn", thread_id="mcp-delta-thread")
        assert len(first_model.calls) > second_call_index
        second_messages = first_model.calls[second_call_index]
        second_deltas = _delta_messages(second_messages)
        assert len(second_deltas) == 1
        assert second_deltas[0] == first_deltas[0]

        agent.close()

    _write_mcp("Use nu50demo only for trusted reads.")
    second_model = _MessageCaptureModel("Second MCP delta response")

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=second_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(
            workspace_root=str(tmp_path),
            bundle_dir=str(bundle_dir),
            api_key="sk-test-integration",
        )
        await agent.ainit()
        _set_agent_checkpointer(agent, checkpointer)

        await agent.ainvoke("third turn", thread_id="mcp-delta-thread")
        assert second_model.calls
        third_messages = second_model.calls[0]
        third_deltas = _delta_messages(third_messages)
        assert len(third_deltas) == 2
        assert "Use nu50demo carefully." in third_deltas[0]
        assert "Use nu50demo only for trusted reads." in third_deltas[1]

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_memoizes_prompt_sections_between_builds(tmp_path):
    """Pattern 6: prompt sections should be cached across repeated prompt assembly."""
    from core.runtime import prompts as prompt_builders
    from core.runtime.agent import LeonAgent

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

    with (
        patch("core.runtime.prompts.build_context_section", side_effect=counted_context),
        patch("core.runtime.prompts.build_rules_section", side_effect=counted_rules),
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
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
    from core.runtime import prompts as prompt_builders
    from core.runtime.agent import LeonAgent

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

    with (
        patch("core.runtime.prompts.build_context_section", side_effect=counted_context),
        patch("core.runtime.prompts.build_rules_section", side_effect=counted_rules),
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()
        agent.agent.aclear = AsyncMock()

        assert counts == {"context": 1, "rules": 1}

        await agent.aclear_thread("prompt-clear-thread")

        assert counts == {"context": 2, "rules": 2}

        agent.close()


def test_build_rules_section_unifies_core_risk_and_tool_preferences():
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
    assert "Do not guess URLs" in rules
    assert "Do not add features, refactor code, or make speculative abstractions" in rules
    assert "Don't create helpers, utilities, or abstractions for one-time operations" in rules
    assert "Don't add error handling, fallbacks, or validation for scenarios that can't happen" in rules
    assert "Prefer dedicated tools over `Bash`" in rules
    assert "Use `Read` instead of `cat`, `head`, or `tail`." in rules
    assert "Use `Glob`/`Grep` for file discovery and content search before falling back to `Bash`." in rules
    assert "Ask before destructive, hard-to-reverse, or shared-state actions" in rules
    assert (
        "Examples: deleting files, force-pushing, dropping tables, killing unfamiliar processes, modifying shared infrastructure." in rules
    )
    assert "Background Task Description" not in rules


def test_leon_agent_chat_identity_prompt_uses_participant_id_tool_wording():
    from core.runtime.agent import LeonAgent

    agent = object.__new__(LeonAgent)
    agent._build_system_prompt = lambda: "BASE"
    cast(Any, agent).config = SimpleNamespace(system_prompt=None)
    agent._chat_repos = {
        "chat_identity_id": "agent-user-1",
        "owner_id": "human-user-1",
        "user_repo": SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Toad") if uid == "agent-user-1" else SimpleNamespace(id=uid, display_name="Owner")
            )
        ),
    }

    prompt = LeonAgent._compose_system_prompt(agent)

    assert "- Your chat identity id: agent-user-1" in prompt
    assert "- For 1:1 chat tools, use participant_id for the other user's social id." in prompt
    assert "- Your owner: Owner (human user_id: human-user-1)" in prompt
    assert "- Your user_id:" not in prompt


def test_leon_agent_chat_identity_prompt_rejects_user_id_only_runtime_shape() -> None:
    from core.runtime.agent import LeonAgent

    agent = object.__new__(LeonAgent)
    agent._build_system_prompt = lambda: "BASE"
    cast(Any, agent).config = SimpleNamespace(system_prompt=None)
    agent._chat_repos = {
        "user_id": "agent-user-removed",
        "owner_id": "human-user-removed",
        "user_repo": SimpleNamespace(get_by_id=lambda uid: SimpleNamespace(id=uid, display_name=f"resolved:{uid}")),
    }

    with pytest.raises(RuntimeError, match="chat_identity_id"):
        LeonAgent._compose_system_prompt(agent)


def test_leon_agent_chat_tool_wiring_rejects_user_id_only_runtime_shape(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from core.runtime.agent import LeonAgent
    from core.runtime.registry import ToolRegistry

    class _NoopService:
        def __init__(self, *args, **kwargs) -> None:
            return None

    class _NoopRegistry:
        def __init__(self, *args, **kwargs) -> None:
            return None

    class _FakeChatToolService:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("chat tool should not initialize from user_id-only runtime shape")

    monkeypatch.setattr("core.runtime.agent.TaskService", _NoopService)
    monkeypatch.setattr("core.runtime.agent.McpResourceToolService", _NoopService)
    monkeypatch.setattr("core.runtime.agent.ToolSearchService", _NoopService)
    monkeypatch.setattr("core.runtime.agent.AgentRegistry", _NoopRegistry)
    monkeypatch.setattr("core.runtime.agent.AgentService", _NoopService)
    monkeypatch.setattr("messaging.tools.chat_tool_service.ChatToolService", _FakeChatToolService)

    agent = object.__new__(LeonAgent)
    agent._sandbox = SimpleNamespace(name="local", fs=lambda: None, shell=lambda: None)
    agent._tool_registry = ToolRegistry()
    agent.workspace_root = str(tmp_path)
    agent.model_name = "test-model"
    agent._thread_repo = SimpleNamespace()
    agent._user_repo = SimpleNamespace()
    agent.queue_manager = SimpleNamespace()
    agent._web_app = None
    agent.allowed_file_extensions = []
    agent.extra_allowed_paths = []
    agent.enable_audit_log = False
    agent.block_dangerous_commands = False
    agent.block_network_commands = False
    agent.verbose = False
    agent._get_mcp_server_configs = lambda: {}
    agent._chat_repos = {
        "user_id": "thread-user-removed",
        "owner_id": "human-user-removed",
        "messaging_service": SimpleNamespace(),
        "user_repo": SimpleNamespace(),
        "relationship_repo": SimpleNamespace(),
    }
    cast(Any, agent).config = SimpleNamespace(
        tools=SimpleNamespace(
            filesystem=SimpleNamespace(enabled=False),
            search=SimpleNamespace(enabled=False),
            web=SimpleNamespace(enabled=False),
            command=SimpleNamespace(enabled=False),
        ),
        skills=SimpleNamespace(enabled=False, paths=[], skills={}),
    )

    with pytest.raises(RuntimeError, match="chat_identity_id"):
        LeonAgent._init_services(agent)


def test_leon_agent_chat_identity_prompt_accepts_chat_identity_id_without_removed_user_id():
    from core.runtime.agent import LeonAgent

    agent = object.__new__(LeonAgent)
    agent._build_system_prompt = lambda: "BASE"
    cast(Any, agent).config = SimpleNamespace(system_prompt=None)
    agent._chat_repos = {
        "chat_identity_id": "agent-user-2",
        "owner_id": "human-user-2",
        "user_repo": SimpleNamespace(
            get_by_id=lambda uid: (
                SimpleNamespace(id=uid, display_name="Morel") if uid == "agent-user-2" else SimpleNamespace(id=uid, display_name="Owner 2")
            )
        ),
    }

    prompt = LeonAgent._compose_system_prompt(agent)

    assert "- Your chat identity id: agent-user-2" in prompt
    assert "- Your owner: Owner 2 (human user_id: human-user-2)" in prompt


def test_leon_agent_chat_identity_prompt_does_not_bridge_removed_thread_user_id() -> None:
    from core.runtime.agent import LeonAgent

    agent = object.__new__(LeonAgent)
    agent._build_system_prompt = lambda: "BASE"
    cast(Any, agent).config = SimpleNamespace(system_prompt=None)
    agent._thread_repo = SimpleNamespace(get_by_user_id=lambda _uid: pytest.fail("removed thread-user bridge should not be used"))
    agent._chat_repos = {
        "chat_identity_id": "thread-user-3",
        "owner_id": "human-user-3",
        "user_repo": SimpleNamespace(
            get_by_id=lambda uid: (
                None
                if uid == "thread-user-3"
                else SimpleNamespace(id=uid, display_name="Truffle")
                if uid == "agent-user-3"
                else SimpleNamespace(id=uid, display_name="Owner 3")
            )
        ),
    }

    prompt = LeonAgent._compose_system_prompt(agent)

    assert "- Your name: thread-user-3" in prompt
    assert "- Your chat identity id: thread-user-3" in prompt
    assert "- Your owner: Owner 3 (human user_id: human-user-3)" in prompt


def test_leon_agent_chat_tool_wiring_does_not_pass_dead_repo_dependencies(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from core.runtime.agent import LeonAgent
    from core.runtime.registry import ToolRegistry

    captured: dict[str, Any] = {}

    class _NoopService:
        def __init__(self, *args, **kwargs) -> None:
            return None

    class _NoopRegistry:
        def __init__(self, *args, **kwargs) -> None:
            return None

    class _FakeChatToolService:
        def __init__(self, *args, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("core.runtime.agent.TaskService", _NoopService)
    monkeypatch.setattr("core.runtime.agent.McpResourceToolService", _NoopService)
    monkeypatch.setattr("core.runtime.agent.ToolSearchService", _NoopService)
    monkeypatch.setattr("core.runtime.agent.AgentRegistry", _NoopRegistry)
    monkeypatch.setattr("core.runtime.agent.AgentService", _NoopService)
    monkeypatch.setattr("messaging.tools.chat_tool_service.ChatToolService", _FakeChatToolService)

    agent = object.__new__(LeonAgent)
    agent._sandbox = SimpleNamespace(name="local", fs=lambda: None, shell=lambda: None)
    agent._tool_registry = ToolRegistry()
    agent.workspace_root = str(tmp_path)
    agent.model_name = "test-model"
    agent._thread_repo = SimpleNamespace()
    agent._user_repo = SimpleNamespace()
    agent.queue_manager = SimpleNamespace()
    agent._web_app = None
    agent.allowed_file_extensions = []
    agent.extra_allowed_paths = []
    agent.enable_audit_log = False
    agent.block_dangerous_commands = False
    agent.block_network_commands = False
    agent.verbose = False
    agent._get_mcp_server_configs = lambda: {}
    agent._chat_repos = {
        "chat_identity_id": "thread-user-9",
        "owner_id": "human-user-9",
        "messaging_service": SimpleNamespace(),
        "chat_member_repo": object(),
        "messages_repo": object(),
        "user_repo": SimpleNamespace(),
        "relationship_repo": SimpleNamespace(),
    }
    cast(Any, agent).config = SimpleNamespace(
        tools=SimpleNamespace(
            filesystem=SimpleNamespace(enabled=False),
            search=SimpleNamespace(enabled=False),
            web=SimpleNamespace(enabled=False),
            command=SimpleNamespace(enabled=False),
        ),
        skills=SimpleNamespace(enabled=False, paths=[], skills={}),
    )

    LeonAgent._init_services(agent)

    assert captured["chat_identity_id"] == "thread-user-9"
    assert "user_id" not in captured
    assert "chat_member_repo" not in captured
    assert "messages_repo" not in captured
    assert "owner_id" not in captured
    assert "relationship_repo" not in captured
    assert "user_repo" not in captured
    assert "thread_repo" not in captured


def test_build_rules_section_includes_function_result_clearing_guidance_when_spill_buffer_enabled():
    from core.runtime.prompts import build_rules_section

    rules = build_rules_section(
        is_sandbox=False,
        working_dir="/repo",
        workspace_root="/repo",
        spill_buffer_enabled=True,
        spill_keep_recent=3,
    )

    assert "**Function Result Clearing**" in rules
    assert "Old tool results may be cleared from context to free up space." in rules
    assert "The 3 most recent results are always kept." in rules
    assert "write down any important information you might need later in your response" in rules


def test_build_rules_section_omits_function_result_clearing_guidance_when_spill_buffer_disabled():
    from core.runtime.prompts import build_rules_section

    rules = build_rules_section(
        is_sandbox=False,
        working_dir="/repo",
        workspace_root="/repo",
        spill_buffer_enabled=False,
        spill_keep_recent=3,
    )

    assert "**Function Result Clearing**" not in rules


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_session_start_hook_runs_on_ainit(tmp_path):
    from core.runtime.agent import LeonAgent

    mock_model = _mock_model("Session start response")
    seen = []

    def on_start(payload):
        seen.append(payload)

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
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

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
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

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
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
        self.turn_tool_names.append([_require_tool_name(tool) for tool in self._tools if isinstance(tool, dict)])
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
        self.turn_tool_names.append([_require_tool_name(tool) for tool in self._tools if isinstance(tool, dict)])
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
        self.turn_tool_names.append([_require_tool_name(tool) for tool in self._tools if isinstance(tool, dict)])
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


class _DeferredInlineSelectProbeModel:
    def __init__(self):
        self.turn_tool_names: list[list[str]] = []
        self._tools: list[dict] = []
        self._turn = 0

    def bind_tools(self, tools):
        self._tools = list(tools or [])
        self.turn_tool_names.append([_require_tool_name(tool) for tool in self._tools if isinstance(tool, dict)])
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
                tool_calls=[{"name": "tool_search", "args": {"query": "select:Read,TaskCreate"}, "id": "tc-search"}],
            )
        self._turn += 1
        return AIMessage(content="after-inline-select")


class _DeferredResumeProbeModel:
    def __init__(self):
        self.turn_tool_names: list[list[str]] = []
        self._tools: list[dict] = []

    def bind_tools(self, tools):
        self._tools = list(tools or [])
        self.turn_tool_names.append([_require_tool_name(tool) for tool in self._tools if isinstance(tool, dict)])
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

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=probe_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
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

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=probe_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        result = await agent.ainvoke("discover then run deferred task tool", thread_id="test-deferred-execution")

        assert result["reason"] == "completed"
        assert len(probe_model.turn_tool_names) >= 2
        assert "TaskCreate" not in probe_model.turn_tool_names[0]
        assert "TaskCreate" in probe_model.turn_tool_names[1]

        task_tool_messages = [msg for msg in result["messages"] if isinstance(msg, ToolMessage) and msg.tool_call_id == "tc-task-create"]
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

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=probe_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
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
async def test_leon_agent_tool_search_exact_select_fails_loudly_for_inline_tools(tmp_path):
    """Exact select should surface inline-tool misuse as a tool_use_error in the live loop."""
    from core.runtime.agent import LeonAgent

    probe_model = _DeferredInlineSelectProbeModel()

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=probe_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        result = await agent.ainvoke("probe inline select", thread_id="test-inline-select")

        assert result["reason"] == "completed"
        tool_messages = [msg for msg in result["messages"] if isinstance(msg, ToolMessage) and msg.tool_call_id == "tc-search"]
        assert len(tool_messages) == 1
        assert "<tool_use_error>" in str(tool_messages[0].content)
        assert "inline/already-available tools: Read" in str(tool_messages[0].content)
        assert any(isinstance(msg, AIMessage) and msg.content == "after-inline-select" for msg in result["messages"])

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_restores_discovered_deferred_tools_after_restart(tmp_path):
    """Restarting the loop on the same thread should restore prior deferred discoveries from history."""
    from core.runtime.agent import LeonAgent

    checkpointer = _MemoryCheckpointer()
    discovery_model = _DeferredDiscoveryProbeModel()

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=discovery_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()
        _set_agent_checkpointer(agent, checkpointer)

        result = await agent.ainvoke("discover task tools", thread_id="resume-thread")
        assert result["reason"] == "completed"
        agent.close()

    resume_model = _DeferredResumeProbeModel()

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=resume_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()
        _set_agent_checkpointer(agent, checkpointer)

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

    mock_model = MagicMock()
    mock_model.bind_tools.return_value = mock_model
    mock_model.with_config.return_value = mock_model
    mock_model.configurable_fields.return_value = mock_model
    mock_model.ainvoke = AsyncMock(
        side_effect=[
            AIMessage(content="Response for thread-A"),
            AIMessage(content="Response for thread-B"),
        ]
    )

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
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

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
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

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()

        async def fake_stream(*args, **kwargs):
            yield ("messages", ("first", {"langgraph_node": "agent"}))
            yield ("updates", {"agent": {"messages": [AIMessage(content="done")]}})

        agent.agent.astream = fake_stream
        _set_agent_runtime(agent, SimpleNamespace(cost=0.75))

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

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()
        _set_agent_checkpointer(agent, checkpointer)
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

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=mock_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()
        _set_agent_checkpointer(agent, checkpointer)

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

        assert result.request_messages is not None
        assert [msg.content for msg in result.request_messages] == ["fresh-1", "fresh-2"]

        agent.close()


@pytest.mark.asyncio
@_patch_env_api_key()
async def test_leon_agent_persists_summary_store_after_second_turn_compaction(tmp_path):
    from core.runtime.agent import LeonAgent
    from core.runtime.middleware.memory.summary_store import SummaryStore

    checkpointer = _MemoryCheckpointer()
    probe_model = _DirectCompactionProbeModel()

    with (
        patch("core.runtime.agent.LeonAgent._create_model", return_value=probe_model),
        patch("core.runtime.agent.LeonAgent._init_async_components", return_value=(None, [])),
        patch("core.runtime.agent.LeonAgent._init_checkpointer", new_callable=AsyncMock, return_value=None),
    ):
        agent = LeonAgent(workspace_root=str(tmp_path), api_key="sk-test-integration")
        await agent.ainit()
        _set_agent_checkpointer(agent, checkpointer)

        store = SummaryStore(tmp_path / "summary.db")
        agent._memory_middleware.summary_store = store
        agent._memory_middleware._compaction_trigger_tokens = 1000
        agent._memory_middleware.compactor.keep_recent_tokens = 10

        turn1 = await agent.ainvoke("A" * 12000, thread_id="agent-compaction-thread")
        assert turn1["reason"] == "completed"
        assert store.get_latest_summary("agent-compaction-thread") is None

        turn2 = await agent.ainvoke("B" * 12000, thread_id="agent-compaction-thread")
        assert turn2["reason"] == "completed"
        assert probe_model.summary_calls == 1
        assert agent._memory_middleware._cached_summary is not None
        assert agent._memory_middleware._compact_up_to_index > 0

        summary = store.get_latest_summary("agent-compaction-thread")
        assert summary is not None
        assert summary.compact_up_to_index == agent._memory_middleware._compact_up_to_index
        assert "Request/Intent" in summary.summary_text

        agent.close()
