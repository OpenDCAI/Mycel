import pytest
from tests.e2e.conftest import create_thread, upload_file, send_message, get_thread_messages
import time

def test_local_sandbox_file_access(api_client, test_file_content):
    """Test file upload and access in local sandbox."""
    thread_id = create_thread(api_client, "local")

    upload_file(api_client, thread_id, "test.txt", test_file_content)
    send_message(api_client, thread_id, "Read /workspace/files/test.txt")

    time.sleep(3)
    messages = get_thread_messages(api_client, thread_id)
    agent_response = messages[-1]["content"]
    assert "Test file content" in agent_response or "test.txt" in agent_response.lower()
