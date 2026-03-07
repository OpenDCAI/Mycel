import pytest
import time
from tests.e2e.conftest import create_thread, upload_file, send_message, get_thread_messages

def test_docker_workspace_sync(api_client, test_file_content):
    """Test file upload and access in Docker sandbox."""
    thread_id = create_thread(api_client, "docker")

    # Upload file
    result = upload_file(api_client, thread_id, "test.txt", test_file_content)
    assert "relative_path" in result

    # Ask agent to read the file
    send_message(api_client, thread_id, "Read the file /workspace/files/test.txt and tell me its content")

    # Wait for agent response
    time.sleep(5)

    # Verify agent could access the file
    messages = get_thread_messages(api_client, thread_id)
    assert len(messages) >= 2  # User message + agent response
    agent_response = messages[-1]["content"]
    assert "Test file content" in agent_response or "test.txt" in agent_response.lower()
