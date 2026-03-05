"""后台任务状态存储系统，用于管理 Bash 命令和 Agent 任务。"""

import asyncio
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TaskEntry:
    """后台任务条目。"""

    task_id: str
    task_type: Literal["bash", "agent"]
    thread_id: str
    status: Literal["running", "completed", "error"]

    # Bash 专属
    command_line: str | None = None
    stdout_buffer: list[str] | None = None
    stderr_buffer: list[str] | None = None
    exit_code: int | None = None

    # Agent 专属
    description: str | None = None
    subagent_type: str | None = None
    text_buffer: list[str] | None = None
    result: str | None = None

    # 通用
    error: str | None = None

    # 内部引用（不暴露给 API）
    _process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    _async_task: asyncio.Task | None = field(default=None, repr=False)


class BackgroundTaskRegistry:
    """后台任务注册表，线程安全的任务状态管理。"""

    MAX_BUFFER_LINES = 1000

    def __init__(self):
        self._tasks: dict[str, TaskEntry] = {}
        self._lock = asyncio.Lock()

    async def register(self, entry: TaskEntry) -> None:
        """注册新任务。"""
        async with self._lock:
            self._tasks[entry.task_id] = entry

    async def update(self, task_id: str, **kwargs) -> None:
        """更新任务状态。"""
        async with self._lock:
            entry = self._tasks.get(task_id)
            if entry is None:
                raise KeyError(f"Task {task_id} not found")

            # 更新字段
            for key, value in kwargs.items():
                if hasattr(entry, key):
                    setattr(entry, key, value)

            # 截断 buffer 到最大行数
            if entry.stdout_buffer and len(entry.stdout_buffer) > self.MAX_BUFFER_LINES:
                entry.stdout_buffer = entry.stdout_buffer[-self.MAX_BUFFER_LINES :]
            if entry.stderr_buffer and len(entry.stderr_buffer) > self.MAX_BUFFER_LINES:
                entry.stderr_buffer = entry.stderr_buffer[-self.MAX_BUFFER_LINES :]
            if entry.text_buffer and len(entry.text_buffer) > self.MAX_BUFFER_LINES:
                entry.text_buffer = entry.text_buffer[-self.MAX_BUFFER_LINES :]

    async def get(self, task_id: str) -> TaskEntry | None:
        """获取任务。"""
        async with self._lock:
            return self._tasks.get(task_id)

    async def list_by_thread(self, thread_id: str) -> list[TaskEntry]:
        """列出线程的所有任务。"""
        async with self._lock:
            return [entry for entry in self._tasks.values() if entry.thread_id == thread_id]

    async def cleanup_thread(self, thread_id: str) -> None:
        """清理线程任务。"""
        async with self._lock:
            # 收集需要清理的任务
            to_remove = [task_id for task_id, entry in self._tasks.items() if entry.thread_id == thread_id]

            # 取消运行中的任务
            for task_id in to_remove:
                entry = self._tasks[task_id]
                if entry._async_task and not entry._async_task.done():
                    entry._async_task.cancel()
                if entry._process:
                    try:
                        entry._process.terminate()
                    except ProcessLookupError:
                        pass

            # 删除任务
            for task_id in to_remove:
                del self._tasks[task_id]
