import httpx
import pytest
from pathlib import Path

@pytest.fixture
def api_client():
    """HTTP client for backend API."""
    return httpx.Client(base_url="http://127.0.0.1:8003", timeout=30.0, trust_env=False)

@pytest.fixture
def test_file_content():
    """Sample file content for upload tests."""
    return b"Test file content for workspace sync"

def create_thread(client: httpx.Client, sandbox_type: str) -> str:
    """Create a thread and return thread_id."""
    response = client.post("/api/threads", json={"sandbox": sandbox_type})
    assert response.status_code == 200
    return response.json()["thread_id"]

def upload_file(client: httpx.Client, thread_id: str, filename: str, content: bytes) -> dict:
    """Upload a file to thread workspace."""
    files = {"file": (filename, content)}
    response = client.post(f"/api/threads/{thread_id}/workspace/upload", files=files)
    assert response.status_code == 200
    return response.json()

def send_message(client: httpx.Client, thread_id: str, message: str) -> dict:
    """Send message to agent."""
    response = client.post(f"/api/threads/{thread_id}/messages", json={"message": message})
    assert response.status_code == 200
    return response.json()

def get_thread_messages(client: httpx.Client, thread_id: str) -> list:
    """Get all messages in thread."""
    response = client.get(f"/api/threads/{thread_id}")
    assert response.status_code == 200
    return response.json()["messages"]
