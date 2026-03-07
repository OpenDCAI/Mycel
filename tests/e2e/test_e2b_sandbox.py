import pytest
from tests.e2e.conftest import create_thread, upload_file, send_message, get_thread_messages
import time

def test_e2b_sandbox_file_access(api_client, test_file_content):
    """Test file upload and access in E2B sandbox."""
    thread_id = create_thread(api_client, "e2b")

    upload_file(api_client, thread_id, "test.txt", test_file_content)
    send_message(api_client, thread_id, "Read /workspace/files/test.txt")

    time.sleep(5)
    messages = get_thread_messages(api_client, thread_id)
    agent_response = messages[-1]["content"]
    assert "Test file content" in agent_response or "test.txt" in agent_response.lower()
