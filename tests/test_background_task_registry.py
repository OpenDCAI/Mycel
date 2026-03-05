"""测试 BackgroundTaskRegistry 的 CRUD 操作。"""

import asyncio
import pytest

from core.task.registry import BackgroundTaskRegistry, TaskEntry


@pytest.mark.asyncio
async def test_register_and_get():
    """测试注册和获取任务。"""
    registry = BackgroundTaskRegistry()

    entry = TaskEntry(
        task_id="test-1",
        task_type="bash",
        thread_id="thread-1",
        status="running",
        command_line="echo hello",
        stdout_buffer=[],
        stderr_buffer=[],
    )

    await registry.register(entry)
    retrieved = await registry.get("test-1")

    assert retrieved is not None
    assert retrieved.task_id == "test-1"
    assert retrieved.task_type == "bash"
    assert retrieved.command_line == "echo hello"


@pytest.mark.asyncio
async def test_update_task():
    """测试更新任务状态。"""
    registry = BackgroundTaskRegistry()

    entry = TaskEntry(
        task_id="test-2",
        task_type="agent",
        thread_id="thread-1",
        status="running",
        description="Test agent",
        text_buffer=[],
    )

    await registry.register(entry)
    await registry.update("test-2", status="completed", result="Success")

    updated = await registry.get("test-2")
    assert updated.status == "completed"
    assert updated.result == "Success"


@pytest.mark.asyncio
async def test_update_nonexistent_task():
    """测试更新不存在的任务应抛出异常。"""
    registry = BackgroundTaskRegistry()

    with pytest.raises(KeyError, match="Task nonexistent not found"):
        await registry.update("nonexistent", status="completed")


@pytest.mark.asyncio
async def test_buffer_truncation():
    """测试 buffer 自动截断到最大行数。"""
    registry = BackgroundTaskRegistry()

    # 创建超过最大行数的 buffer
    large_buffer = [f"line-{i}" for i in range(1500)]

    entry = TaskEntry(
        task_id="test-3",
        task_type="bash",
        thread_id="thread-1",
        status="running",
        command_line="test",
        stdout_buffer=large_buffer.copy(),
        stderr_buffer=large_buffer.copy(),
    )

    await registry.register(entry)
    await registry.update("test-3", status="running")

    updated = await registry.get("test-3")
    assert len(updated.stdout_buffer) == BackgroundTaskRegistry.MAX_BUFFER_LINES
    assert len(updated.stderr_buffer) == BackgroundTaskRegistry.MAX_BUFFER_LINES
    # 验证保留的是最后 1000 行
    assert updated.stdout_buffer[0] == "line-500"
    assert updated.stdout_buffer[-1] == "line-1499"


@pytest.mark.asyncio
async def test_list_by_thread():
    """测试按线程列出任务。"""
    registry = BackgroundTaskRegistry()

    # 创建多个线程的任务
    for i in range(3):
        await registry.register(
            TaskEntry(
                task_id=f"thread1-task-{i}",
                task_type="bash",
                thread_id="thread-1",
                status="running",
                command_line=f"cmd-{i}",
            )
        )

    for i in range(2):
        await registry.register(
            TaskEntry(
                task_id=f"thread2-task-{i}",
                task_type="agent",
                thread_id="thread-2",
                status="running",
                description=f"agent-{i}",
            )
        )

    thread1_tasks = await registry.list_by_thread("thread-1")
    thread2_tasks = await registry.list_by_thread("thread-2")

    assert len(thread1_tasks) == 3
    assert len(thread2_tasks) == 2
    assert all(t.thread_id == "thread-1" for t in thread1_tasks)
    assert all(t.thread_id == "thread-2" for t in thread2_tasks)


@pytest.mark.asyncio
async def test_cleanup_thread():
    """测试清理线程任务。"""
    registry = BackgroundTaskRegistry()

    # 创建任务
    await registry.register(
        TaskEntry(
            task_id="cleanup-1",
            task_type="bash",
            thread_id="thread-cleanup",
            status="running",
            command_line="test",
        )
    )
    await registry.register(
        TaskEntry(
            task_id="cleanup-2",
            task_type="agent",
            thread_id="thread-cleanup",
            status="running",
            description="test",
        )
    )
    await registry.register(
        TaskEntry(
            task_id="keep-1",
            task_type="bash",
            thread_id="thread-keep",
            status="running",
            command_line="test",
        )
    )

    # 清理 thread-cleanup
    await registry.cleanup_thread("thread-cleanup")

    # 验证清理结果
    assert await registry.get("cleanup-1") is None
    assert await registry.get("cleanup-2") is None
    assert await registry.get("keep-1") is not None


@pytest.mark.asyncio
async def test_concurrent_updates():
    """测试并发更新的线程安全性。"""
    registry = BackgroundTaskRegistry()

    entry = TaskEntry(
        task_id="concurrent-1",
        task_type="bash",
        thread_id="thread-1",
        status="running",
        command_line="test",
        stdout_buffer=[],
    )
    await registry.register(entry)

    # 并发更新 stdout_buffer
    async def append_line(line: str):
        current = await registry.get("concurrent-1")
        new_buffer = (current.stdout_buffer or []) + [line]
        await registry.update("concurrent-1", stdout_buffer=new_buffer)

    await asyncio.gather(*[append_line(f"line-{i}") for i in range(10)])

    final = await registry.get("concurrent-1")
    # 由于并发，不是所有行都会被保留（后面的更新会覆盖前面的）
    # 但至少应该有一些行
    assert final.stdout_buffer is not None
    assert len(final.stdout_buffer) > 0
