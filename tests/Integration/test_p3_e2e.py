"""
P3 端到端测试：验证 Background Task 统一系统
"""

import asyncio
import os

import httpx
import pytest

from agent import LeonAgent

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)


@pytest.mark.asyncio
async def test_bash_task_lifecycle():
    """测试 Bash 任务完整生命周期"""
    # 1. 创建 agent 并执行 bash 命令
    agent = LeonAgent()
    thread_id = "test-bash-e2e"
    config = {"configurable": {"thread_id": thread_id}}

    # 执行一个简单的 bash 命令（后台运行）
    async for chunk in agent.agent.astream(
        {"messages": [{"role": "user", "content": "Run 'sleep 2 && echo done' in background"}]},
        config=config,
        stream_mode="updates",
    ):
        pass  # 等待命令启动

    # 2. 通过 API 查询任务列表
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://127.0.0.1:8003/api/threads/{thread_id}/tasks")
        tasks = response.json()

        # 验证任务已注册
        assert len(tasks) > 0, "应该有至少一个任务"
        bash_task = next((t for t in tasks if t["task_type"] == "bash"), None)
        assert bash_task is not None, "应该有 bash 类型的任务"
        assert bash_task["status"] in ["running", "completed"], f"任务状态应该是 running 或 completed，实际: {bash_task['status']}"

        task_id = bash_task["task_id"]

        # 3. 获取任务详情
        response = await client.get(f"http://127.0.0.1:8003/api/threads/{thread_id}/tasks/{task_id}")
        task_detail = response.json()

        assert task_detail["task_id"] == task_id
        assert task_detail["task_type"] == "bash"
        assert "command_line" in task_detail

        # 4. 等待任务完成
        await asyncio.sleep(3)

        # 5. 再次查询，验证状态更新
        response = await client.get(f"http://127.0.0.1:8003/api/threads/{thread_id}/tasks/{task_id}")
        final_task = response.json()

        assert final_task["status"] == "completed", f"任务应该已完成，实际状态: {final_task['status']}"
        assert final_task["exit_code"] == 0, f"退出码应该是 0，实际: {final_task['exit_code']}"

    agent.close()


@pytest.mark.asyncio
async def test_agent_task_lifecycle():
    """测试 Agent 任务完整生命周期"""
    # 1. 创建 agent 并执行 task agent
    agent = LeonAgent()
    thread_id = "test-agent-e2e"
    config = {"configurable": {"thread_id": thread_id}}

    # 创建一个后台 task agent
    async for chunk in agent.agent.astream(
        {"messages": [{"role": "user", "content": "Create a background task to analyze the current directory"}]},
        config=config,
        stream_mode="updates",
    ):
        pass

    # 2. 通过 API 查询任务列表
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://127.0.0.1:8003/api/threads/{thread_id}/tasks")
        tasks = response.json()

        # 验证任务已注册
        agent_task = next((t for t in tasks if t["task_type"] == "agent"), None)
        if agent_task:  # 如果有 agent 任务
            task_id = agent_task["task_id"]

            # 3. 获取任务详情
            response = await client.get(f"http://127.0.0.1:8003/api/threads/{thread_id}/tasks/{task_id}")
            task_detail = response.json()

            assert task_detail["task_type"] == "agent"
            assert "description" in task_detail or "subagent_type" in task_detail

    agent.close()


@pytest.mark.asyncio
async def test_task_cancel():
    """测试任务取消功能"""
    agent = LeonAgent()
    thread_id = "test-cancel-e2e"
    config = {"configurable": {"thread_id": thread_id}}

    # 启动一个长时间运行的命令
    async for chunk in agent.agent.astream(
        {"messages": [{"role": "user", "content": "Run 'sleep 10' in background"}]},
        config=config,
        stream_mode="updates",
    ):
        pass

    await asyncio.sleep(1)  # 等待命令启动

    async with httpx.AsyncClient() as client:
        # 获取任务列表
        response = await client.get(f"http://127.0.0.1:8003/api/threads/{thread_id}/tasks")
        tasks = response.json()

        if len(tasks) > 0:
            task_id = tasks[0]["task_id"]

            # 取消任务
            response = await client.post(f"http://127.0.0.1:8003/api/threads/{thread_id}/tasks/{task_id}/cancel")
            result = response.json()

            assert result["success"] is True, "取消应该成功"

            # 验证状态更新
            await asyncio.sleep(0.5)
            response = await client.get(f"http://127.0.0.1:8003/api/threads/{thread_id}/tasks/{task_id}")
            task = response.json()

            assert task["status"] == "error", f"任务状态应该是 error，实际: {task['status']}"
            assert "Cancelled" in task.get("error", ""), "错误信息应该包含 Cancelled"

    agent.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
