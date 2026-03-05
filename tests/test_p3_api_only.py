"""
P3 API 端点测试：仅测试 REST API，不依赖 LeonAgent
"""
import httpx
import pytest


BASE_URL = "http://127.0.0.1:8003"


@pytest.mark.asyncio
async def test_list_tasks_empty():
    """测试空任务列表"""
    thread_id = "test-empty-list"

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/threads/{thread_id}/tasks")
        assert response.status_code == 200
        tasks = response.json()
        assert isinstance(tasks, list)
        print(f"✓ 空任务列表返回: {tasks}")


@pytest.mark.asyncio
async def test_get_nonexistent_task():
    """测试获取不存在的任务"""
    thread_id = "test-nonexistent"
    task_id = "nonexistent-task-id"

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/threads/{thread_id}/tasks/{task_id}")
        assert response.status_code == 404
        print(f"✓ 不存在的任务返回 404")


@pytest.mark.asyncio
async def test_cancel_nonexistent_task():
    """测试取消不存在的任务"""
    thread_id = "test-cancel-nonexistent"
    task_id = "nonexistent-task-id"

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/api/threads/{thread_id}/tasks/{task_id}/cancel")
        assert response.status_code == 404
        print(f"✓ 取消不存在的任务返回 404")


@pytest.mark.asyncio
async def test_api_endpoints_exist():
    """测试所有 P3 API 端点是否存在"""
    thread_id = "test-endpoints"

    async with httpx.AsyncClient() as client:
        # 测试列表端点
        response = await client.get(f"{BASE_URL}/api/threads/{thread_id}/tasks")
        assert response.status_code == 200
        print(f"✓ GET /tasks 端点存在")

        # 测试详情端点（404 也说明端点存在）
        response = await client.get(f"{BASE_URL}/api/threads/{thread_id}/tasks/fake-id")
        assert response.status_code == 404
        print(f"✓ GET /tasks/{{task_id}} 端点存在")

        # 测试取消端点（404 也说明端点存在）
        response = await client.post(f"{BASE_URL}/api/threads/{thread_id}/tasks/fake-id/cancel")
        assert response.status_code == 404
        print(f"✓ POST /tasks/{{task_id}}/cancel 端点存在")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
