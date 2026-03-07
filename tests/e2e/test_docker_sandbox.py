import pytest
from tests.e2e.conftest import create_thread, upload_file, send_message, get_thread_messages
import time

def test_docker_sandbox_file_access(api_client, test_file_content):
    """Test file upload and access in Docker sandbox."""
    thread_id = create_thread(api_client, "docker")

    upload_file(api_client, thread_id, "test.txt", test_file_content)
    send_message(api_client, thread_id, "Read /workspace/files/test.txt and tell me its exact content")

    time.sleep(5)
    messages = get_thread_messages(api_client, thread_id)
    agent_response = messages[-1]["content"]
    assert "Test file content" in agent_response
