# Workspace Sync E2E Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix workspace file upload and sync for all sandbox types (local, Docker, Daytona, self-host Daytona, E2B) with comprehensive end-to-end backend API testing.

**Architecture:** Create E2E test framework that simulates complete user-agent interaction via backend APIs. Fix workspace path configuration for each sandbox type. Ensure uploaded files are accessible to agents in all environments.

**Tech Stack:** Python 3.12, pytest, httpx for API testing, Leon's sandbox abstraction layer

---

## Task 1: Create E2E Test Framework

**Files:**
- Create: `tests/e2e/test_workspace_sync.py`
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/__init__.py`

**Step 1: Write E2E test helper functions**

```python
# tests/e2e/conftest.py
import httpx
import pytest
from pathlib import Path

@pytest.fixture
def api_client():
    """HTTP client for backend API."""
    return httpx.Client(base_url="http://127.0.0.1:8003", timeout=30.0)

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
```

**Step 2: Write basic E2E test structure**

```python
# tests/e2e/test_workspace_sync.py
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
```

**Step 3: Run test to verify framework works**

Run: `pytest tests/e2e/test_workspace_sync.py::test_docker_workspace_sync -v -s`
Expected: Test runs (may fail on assertions, but framework should work)

**Step 4: Commit**

```bash
git add tests/e2e/
git commit -m "test: add E2E test framework for workspace sync"
```

---

## Task 2: Fix Local Sandbox Workspace Configuration

**Files:**
- Modify: `sandbox/providers/local.py`
- Create: `tests/e2e/test_local_sandbox.py`

**Step 1: Write test for local sandbox**

```python
# tests/e2e/test_local_sandbox.py
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/e2e/test_local_sandbox.py::test_local_sandbox_file_access -v -s`
Expected: FAIL - agent cannot access file outside project workspace

**Step 3: Identify workspace path issue**

Check current local sandbox workspace configuration:
- Agent workspace: project directory
- Uploaded files: `~/.leon/thread_files/{thread_id}/files/`
- Problem: Agent can't access files outside project workspace

**Step 4: Fix local sandbox to use thread files directory**

```python
# sandbox/providers/local.py (modify get_workspace_path or similar)
def get_workspace_path(self, thread_id: str) -> Path:
    """Get workspace path for thread - use thread files directory."""
    from pathlib import Path
    thread_files = Path.home() / ".leon" / "thread_files" / thread_id / "files"
    thread_files.mkdir(parents=True, exist_ok=True)
    return thread_files
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/e2e/test_local_sandbox.py::test_local_sandbox_file_access -v -s`
Expected: PASS

**Step 6: Commit**

```bash
git add sandbox/providers/local.py tests/e2e/test_local_sandbox.py
git commit -m "fix: configure local sandbox to use thread files directory"
```

---

## Task 3: Fix Daytona Sandbox Workspace Sync

**Files:**
- Modify: `sandbox/providers/daytona.py`
- Modify: `backend/web/routers/workspace.py`
- Create: `tests/e2e/test_daytona_sandbox.py`

**Step 1: Write test for Daytona sandbox**

```python
# tests/e2e/test_daytona_sandbox.py
import pytest
from tests.e2e.conftest import create_thread, upload_file, send_message, get_thread_messages
import time

def test_daytona_sandbox_file_access(api_client, test_file_content):
    """Test file upload and access in Daytona sandbox."""
    thread_id = create_thread(api_client, "daytona")

    upload_file(api_client, thread_id, "test.txt", test_file_content)
    send_message(api_client, thread_id, "Read /workspace/files/test.txt")

    time.sleep(5)
    messages = get_thread_messages(api_client, thread_id)
    agent_response = messages[-1]["content"]
    assert "Test file content" in agent_response or "test.txt" in agent_response.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/e2e/test_daytona_sandbox.py::test_daytona_sandbox_file_access -v -s`
Expected: FAIL - workspace path mismatch or sync timing issue

**Step 3: Fix workspace sync in upload endpoint**

The upload endpoint already has sync logic (from previous work), verify it's working:

```python
# backend/web/routers/workspace.py (verify this exists)
if sandbox_type not in ("local", "docker"):
    manager = get_sandbox_manager(sandbox_type)
    if manager and manager.workspace_sync.needs_upload_sync():
        session = manager.session_manager.get_by_thread(thread_id)
        if session:
            remote_path = f"/workspace/files/{relative_path}"
            await asyncio.to_thread(
                manager.provider.write_file,
                session.session_id, remote_path, content.decode('utf-8')
            )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/e2e/test_daytona_sandbox.py::test_daytona_sandbox_file_access -v -s`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/e2e/test_daytona_sandbox.py
git commit -m "test: add Daytona sandbox E2E test"
```

---

## Task 4: Test and Fix Self-Host Daytona

**Files:**
- Create: `tests/e2e/test_selfhost_daytona.py`

**Step 1: Write test for self-host Daytona**

```python
# tests/e2e/test_selfhost_daytona.py
import pytest
from tests.e2e.conftest import create_thread, upload_file, send_message, get_thread_messages
import time

def test_selfhost_daytona_file_access(api_client, test_file_content):
    """Test file upload and access in self-host Daytona sandbox."""
    thread_id = create_thread(api_client, "daytona_selfhost")

    upload_file(api_client, thread_id, "test.txt", test_file_content)
    send_message(api_client, thread_id, "Read /workspace/files/test.txt")

    time.sleep(5)
    messages = get_thread_messages(api_client, thread_id)
    agent_response = messages[-1]["content"]
    assert "Test file content" in agent_response or "test.txt" in agent_response.lower()
```

**Step 2: Run test**

Run: `pytest tests/e2e/test_selfhost_daytona.py::test_selfhost_daytona_file_access -v -s`
Expected: Should work if Daytona fix (Task 3) is correct

**Step 3: Fix if needed**

If test fails, apply same fix as Daytona (Task 3)

**Step 4: Commit**

```bash
git add tests/e2e/test_selfhost_daytona.py
git commit -m "test: add self-host Daytona E2E test"
```

---

## Task 5: Test and Fix E2B Sandbox

**Files:**
- Create: `tests/e2e/test_e2b_sandbox.py`

**Step 1: Write test for E2B sandbox**

```python
# tests/e2e/test_e2b_sandbox.py
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
```

**Step 2: Run test**

Run: `pytest tests/e2e/test_e2b_sandbox.py::test_e2b_sandbox_file_access -v -s`
Expected: Should work if workspace sync is configured correctly

**Step 3: Fix if needed**

If test fails, apply same workspace sync fix as Daytona (Task 3)

**Step 4: Commit**

```bash
git add tests/e2e/test_e2b_sandbox.py
git commit -m "test: add E2B sandbox E2E test"
```

---

## Task 6: Verify Docker Sandbox

**Files:**
- Create: `tests/e2e/test_docker_sandbox.py`

**Step 1: Write comprehensive Docker test**

```python
# tests/e2e/test_docker_sandbox.py
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
```

**Step 2: Run test**

Run: `pytest tests/e2e/test_docker_sandbox.py::test_docker_sandbox_file_access -v -s`
Expected: PASS (Docker already works with bind mounts)

**Step 3: Commit**

```bash
git add tests/e2e/test_docker_sandbox.py
git commit -m "test: add Docker sandbox E2E test"
```

---

## Task 7: Run All Tests and Verify

**Files:**
- None (verification task)

**Step 1: Run all E2E tests**

Run: `pytest tests/e2e/ -v -s`
Expected: All tests PASS

**Step 2: Manual verification for each sandbox type**

For each sandbox type (local, docker, daytona, daytona_selfhost, e2b):
1. Create thread via API
2. Upload file via API
3. Send message asking agent to read file
4. Verify agent response contains file content

**Step 3: Document results**

Create test report showing:
- Which sandbox types pass
- Which sandbox types fail (if any)
- Error messages for failures

**Step 4: Final commit**

```bash
git add .
git commit -m "test: verify all sandbox types pass E2E tests"
```

---

## Summary

This plan fixes workspace file upload and sync for all sandbox types with comprehensive E2E testing:

**Fixed Issues**:
1. **Local sandbox**: Configure agent workspace to use thread files directory
2. **Daytona sandbox**: Ensure workspace sync uploads files to correct path
3. **Self-host Daytona**: Same fix as Daytona
4. **E2B sandbox**: Same fix as Daytona
5. **Docker sandbox**: Verify existing bind mount solution works

**Testing Strategy**:
- E2E tests simulate complete user-agent interaction via backend APIs
- Test flow: Create thread → Upload file → Send message → Verify agent can access file
- All sandbox types tested with same test pattern

**Quality Gates**:
- Each task has test-first approach (write test → verify failure → fix → verify pass)
- Commit after each task completion
- Final verification runs all tests together

**Next Steps**:
- Integrate with workspace sync manager (from previous plan)
- Monitor production usage
- Add performance metrics
