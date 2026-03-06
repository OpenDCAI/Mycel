"""集成测试：Task Agent 与 BackgroundTaskRegistry 集成。"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.task.registry import BackgroundTaskRegistry, TaskEntry
from core.task.subagent import SubagentRunner
from core.task.types import AgentConfig


@pytest.fixture
def registry():
    """创建 BackgroundTaskRegistry 实例。"""
    return BackgroundTaskRegistry()


@pytest.fixture
def mock_runtime():
    """创建 mock runtime。"""
    runtime = MagicMock()
    runtime.emit_activity_event = MagicMock()
    runtime.emit_subagent_event = MagicMock()
    return runtime


@pytest.fixture
def subagent_runner(registry, mock_runtime):
    """创建 SubagentRunner 实例。"""
    agents = {
        "test_agent": AgentConfig(
            name="Test Agent",
            system_prompt="You are a test agent.",
            tools=["read_file"],
            model="gpt-4o-mini",
        )
    }
    runner = SubagentRunner(
        agents=agents,
        parent_model="gpt-4o-mini",
        workspace_root=Path("/tmp"),
        api_key="test-key",
        registry=registry,
    )
    runner.set_parent_runtime(mock_runtime)
    return runner


@pytest.mark.asyncio
async def test_task_registration(subagent_runner, registry, mock_runtime):
    """测试任务注册到 registry。"""
    # Mock agent creation and execution
    mock_agent = MagicMock()
    mock_agent.astream = AsyncMock()

    # Mock astream to return empty generator
    async def mock_astream(*args, **kwargs):
        if False:
            yield

    mock_agent.astream.return_value = mock_astream()

    # Patch create_agent
    import core.task.subagent
    original_create_agent = core.task.subagent.create_agent

    async def mock_create_agent(*args, **kwargs):
        return mock_agent

    # Temporarily replace create_agent
    from unittest.mock import patch

    with patch('core.task.subagent.create_agent', side_effect=lambda *args, **kwargs: mock_agent):
        # Run background task
        params = {
            "SubagentType": "test_agent",
            "Prompt": "Test prompt",
            "Description": "Test task",
            "RunInBackground": True,
        }

        result = await subagent_runner.run(
            params=params,
            all_middleware=[],
            parent_thread_id="test-thread",
        )

        # Verify task was registered
        assert result.status == "running"
        task_id = result.task_id

        # Check registry
        entry = await registry.get(task_id)
        assert entry is not None
        assert entry.task_type == "agent"
        assert entry.status == "running"
        assert entry.description == "Test task"
        assert entry.subagent_type == "test_agent"
        assert entry.text_buffer == []

        # Verify task_start event was emitted
        mock_runtime.emit_activity_event.assert_called()
        call_args = mock_runtime.emit_activity_event.call_args[0][0]
        assert call_args["event"] == "task_start"
        data = json.loads(call_args["data"])
        assert data["task_id"] == task_id
        assert data["task_type"] == "agent"
        assert data["description"] == "Test task"
        assert data["subagent_type"] == "test_agent"


@pytest.mark.asyncio
async def test_text_buffer_storage(subagent_runner, registry, mock_runtime):
    """测试 text_buffer 存储到 registry。"""
    # Create a mock agent that yields text chunks
    mock_agent = MagicMock()

    async def mock_astream(*args, **kwargs):
        # Simulate AIMessageChunk
        chunk1 = MagicMock()
        chunk1.__class__.__name__ = "AIMessageChunk"
        chunk1.content = "Hello "

        chunk2 = MagicMock()
        chunk2.__class__.__name__ = "AIMessageChunk"
        chunk2.content = "World"

        yield ("messages", (chunk1, {}))
        yield ("messages", (chunk2, {}))

    mock_agent.astream = mock_astream

    # Manually register task first
    task_id = "test-task-123"
    entry = TaskEntry(
        task_id=task_id,
        task_type="agent",
        thread_id="test-thread",
        status="running",
        description="Test",
        subagent_type="test_agent",
        text_buffer=[],
    )
    await registry.register(entry)

    # Execute streaming
    result = await subagent_runner._execute_agent_streaming(
        agent=mock_agent,
        prompt="Test",
        thread_id="test-thread",
        task_id=task_id,
        runtime=mock_runtime,
        description="Test",
    )

    # Verify text was stored in buffer
    entry = await registry.get(task_id)
    assert entry is not None
    assert entry.text_buffer == ["Hello ", "World"]
    assert entry.status == "completed"
    assert entry.result == "Hello World"

    # Verify task_done event was emitted
    calls = [call[0][0] for call in mock_runtime.emit_activity_event.call_args_list]
    done_events = [c for c in calls if c["event"] == "task_done"]
    assert len(done_events) == 1
    assert json.loads(done_events[0]["data"])["task_id"] == task_id


@pytest.mark.asyncio
async def test_task_error_handling(subagent_runner, registry, mock_runtime):
    """测试任务错误处理。"""
    # Create a mock agent that raises an error
    mock_agent = MagicMock()

    async def mock_astream(*args, **kwargs):
        raise ValueError("Test error")
        if False:
            yield  # Make it a generator

    mock_agent.astream = mock_astream

    # Manually register task first
    task_id = "test-task-456"
    entry = TaskEntry(
        task_id=task_id,
        task_type="agent",
        thread_id="test-thread",
        status="running",
        description="Test",
        subagent_type="test_agent",
        text_buffer=[],
    )
    await registry.register(entry)

    # Execute streaming
    result = await subagent_runner._execute_agent_streaming(
        agent=mock_agent,
        prompt="Test",
        thread_id="test-thread",
        task_id=task_id,
        runtime=mock_runtime,
        description="Test",
    )

    # Verify error was stored
    entry = await registry.get(task_id)
    assert entry is not None
    assert entry.status == "error"
    assert entry.error == "Test error"

    # Verify task_error event was emitted
    calls = [call[0][0] for call in mock_runtime.emit_activity_event.call_args_list]
    error_events = [c for c in calls if c["event"] == "task_error"]
    assert len(error_events) == 1
    data = json.loads(error_events[0]["data"])
    assert data["task_id"] == task_id
    assert data["error"] == "Test error"


@pytest.mark.asyncio
async def test_get_task_status_from_registry(subagent_runner, registry):
    """测试从 registry 获取任务状态。"""
    # Register a completed task
    task_id = "test-task-789"
    entry = TaskEntry(
        task_id=task_id,
        task_type="agent",
        thread_id="test-thread",
        status="completed",
        description="Test task",
        subagent_type="test_agent",
        result="Task completed successfully",
    )
    await registry.register(entry)

    # Get status
    result = await subagent_runner.get_task_status(task_id)

    # Verify
    assert result.task_id == task_id
    assert result.status == "completed"
    assert result.result == "Task completed successfully"
    assert result.description == "Test task"


@pytest.mark.asyncio
async def test_task_notification_injection(subagent_runner, registry, mock_runtime):
    """测试 TaskNotification 注入到 queue。"""
    # Mock queue manager
    mock_queue = MagicMock()
    mock_queue.enqueue = MagicMock()
    subagent_runner._queue_manager = mock_queue

    # Create a mock agent
    mock_agent = MagicMock()

    async def mock_astream(*args, **kwargs):
        chunk = MagicMock()
        chunk.__class__.__name__ = "AIMessageChunk"
        chunk.content = "Done"
        yield ("messages", (chunk, {}))

    mock_agent.astream = mock_astream

    # Manually register task
    task_id = "test-task-notif"
    entry = TaskEntry(
        task_id=task_id,
        task_type="agent",
        thread_id="test-thread",
        status="running",
        description="Test",
        subagent_type="test_agent",
        text_buffer=[],
    )
    await registry.register(entry)

    # Execute with parent_thread_id
    result = await subagent_runner._execute_agent(
        agent=mock_agent,
        prompt="Test",
        thread_id="subagent-thread",
        max_turns=10,
        task_id=task_id,
        parent_thread_id="parent-thread",
        description="Test",
    )

    # Verify notification was enqueued
    mock_queue.enqueue.assert_called_once()
    call_args = mock_queue.enqueue.call_args
    xml_content = call_args[0][0]
    thread_id = call_args[0][1]

    assert thread_id == "parent-thread"
    assert f'<task-id>{task_id}</task-id>' in xml_content
    assert '<status>completed</status>' in xml_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
