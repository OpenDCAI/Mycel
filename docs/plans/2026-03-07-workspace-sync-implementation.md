# Workspace Synchronization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement workspace synchronization that uploads files from backend to sandbox on session creation and downloads them back on pause/destroy, with provider-specific strategies (Docker bind mount vs Daytona/E2B upload/download).

**Architecture:** Create a `WorkspaceSync` abstraction that adapts based on provider capabilities. Docker uses existing bind mount (no sync needed). Remote providers (Daytona, E2B) use SDK upload/download methods. Sync hooks integrated into manager lifecycle at session creation, pause, and destroy.

**Tech Stack:** Python 3.11+, Daytona SDK, pathlib, asyncio

---

## Background Context

**Current State:**
- Files uploaded to `~/.leon/thread_files/{thread_id}/files/` on backend
- Docker: bind mount works (files appear immediately in sandbox)
- Daytona/E2B: bind mount attempted but doesn't work (can't mount local dirs to remote sandboxes)
- Agent gets notified of uploads via message prefix

**Problem:**
- Remote sandboxes can't access backend filesystem
- Files uploaded after session creation don't appear in sandbox
- Agent modifications in sandbox aren't persisted back to local workspace

**Solution:**
- Docker: Keep bind mount (optimal, zero-copy)
- Daytona/E2B: Explicit upload/download via SDK
- Unified interface that adapts based on provider capability

---

## Task 1: Create WorkspaceSync Base Class

**Files:**
- Create: `sandbox/workspace_sync.py`
- Test: `tests/sandbox/test_workspace_sync.py`

**Step 1: Write the failing test**

```python
# tests/sandbox/test_workspace_sync.py
import pytest
from pathlib import Path
from sandbox.workspace_sync import WorkspaceSync
from sandbox.provider import ProviderCapability, MountCapability


def test_workspace_sync_initialization():
    """WorkspaceSync should initialize with provider and workspace path."""
    capability = ProviderCapability(
        can_pause=True,
        can_resume=True,
        can_destroy=True,
        mount=MountCapability(supports_mount=True)
    )

    sync = WorkspaceSync(
        provider_capability=capability,
        workspace_root=Path("/tmp/test-workspace")
    )

    assert sync.provider_capability == capability
    assert sync.workspace_root == Path("/tmp/test-workspace")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/sandbox/test_workspace_sync.py::test_workspace_sync_initialization -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'sandbox.workspace_sync'"

**Step 3: Write minimal implementation**

```python
# sandbox/workspace_sync.py
"""Workspace synchronization across different sandbox providers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sandbox.provider import ProviderCapability, SandboxProvider


class WorkspaceSync:
    """Handles workspace file synchronization between backend and sandbox."""

    def __init__(
        self,
        provider_capability: ProviderCapability,
        workspace_root: Path,
    ):
        self.provider_capability = provider_capability
        self.workspace_root = workspace_root
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/sandbox/test_workspace_sync.py::test_workspace_sync_initialization -v`
Expected: PASS

**Step 5: Commit**

```bash
git add sandbox/workspace_sync.py tests/sandbox/test_workspace_sync.py
git commit -m "feat: add WorkspaceSync base class"
```

---

## Task 2: Add Workspace Path Resolution

**Files:**
- Modify: `sandbox/workspace_sync.py`
- Modify: `tests/sandbox/test_workspace_sync.py`

**Step 1: Write the failing test**

```python
# tests/sandbox/test_workspace_sync.py (add to existing file)
def test_get_thread_workspace_path():
    """Should resolve thread-specific workspace directory."""
    sync = WorkspaceSync(
        provider_capability=ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
        ),
        workspace_root=Path("/tmp/workspaces")
    )

    path = sync.get_thread_workspace_path("thread-123")
    assert path == Path("/tmp/workspaces/thread-123/files")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/sandbox/test_workspace_sync.py::test_get_thread_workspace_path -v`
Expected: FAIL with "AttributeError: 'WorkspaceSync' object has no attribute 'get_thread_workspace_path'"

**Step 3: Write minimal implementation**

```python
# sandbox/workspace_sync.py (add method to WorkspaceSync class)
    def get_thread_workspace_path(self, thread_id: str) -> Path:
        """Get the local workspace directory for a thread."""
        return self.workspace_root / thread_id / "files"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/sandbox/test_workspace_sync.py::test_get_thread_workspace_path -v`
Expected: PASS

**Step 5: Commit**

```bash
git add sandbox/workspace_sync.py tests/sandbox/test_workspace_sync.py
git commit -m "feat: add thread workspace path resolution"
```

---

## Task 3: Add Sync Strategy Detection

**Files:**
- Modify: `sandbox/workspace_sync.py`
- Modify: `tests/sandbox/test_workspace_sync.py`

**Step 1: Write the failing test**

```python
# tests/sandbox/test_workspace_sync.py (add to existing file)
def test_needs_upload_sync_for_bind_mount():
    """Bind mount providers don't need upload sync."""
    sync = WorkspaceSync(
        provider_capability=ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
            mount=MountCapability(supports_mount=True)
        ),
        workspace_root=Path("/tmp/workspaces")
    )

    assert sync.needs_upload_sync() is False


def test_needs_upload_sync_for_remote():
    """Remote providers need upload sync."""
    sync = WorkspaceSync(
        provider_capability=ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
            mount=MountCapability(supports_mount=False, supports_copy=True)
        ),
        workspace_root=Path("/tmp/workspaces")
    )

    assert sync.needs_upload_sync() is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/sandbox/test_workspace_sync.py::test_needs_upload_sync_for_bind_mount -v`
Expected: FAIL with "AttributeError: 'WorkspaceSync' object has no attribute 'needs_upload_sync'"

**Step 3: Write minimal implementation**

```python
# sandbox/workspace_sync.py (add method to WorkspaceSync class)
    def needs_upload_sync(self) -> bool:
        """Check if provider needs explicit upload sync (vs bind mount)."""
        return not self.provider_capability.mount.supports_mount
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/sandbox/test_workspace_sync.py -k needs_upload_sync -v`
Expected: PASS (both tests)

**Step 5: Commit**

```bash
git add sandbox/workspace_sync.py tests/sandbox/test_workspace_sync.py
git commit -m "feat: add sync strategy detection"
```

---

## Task 4: Implement Upload Sync for Remote Providers

**Files:**
- Modify: `sandbox/workspace_sync.py`
- Modify: `tests/sandbox/test_workspace_sync.py`

**Step 1: Write the failing test**

```python
# tests/sandbox/test_workspace_sync.py (add to existing file)
from unittest.mock import Mock
import tempfile


def test_upload_workspace_to_sandbox():
    """Should upload all files from workspace to sandbox."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "thread-123" / "files"
        workspace.mkdir(parents=True)
        (workspace / "file1.txt").write_text("content1")
        (workspace / "file2.txt").write_text("content2")

        mock_provider = Mock()
        sync = WorkspaceSync(
            provider_capability=ProviderCapability(
                can_pause=True,
                can_resume=True,
                can_destroy=True,
                mount=MountCapability(supports_mount=False)
            ),
            workspace_root=Path(tmpdir)
        )

        sync.upload_workspace("thread-123", "session-456", mock_provider)
        assert mock_provider.write_file.call_count == 2
```

**Step 2: Run test** → `pytest tests/sandbox/test_workspace_sync.py::test_upload_workspace_to_sandbox -v`

**Step 3: Implement**

```python
# sandbox/workspace_sync.py (add to WorkspaceSync class)
    def upload_workspace(self, thread_id: str, session_id: str, provider: SandboxProvider) -> None:
        """Upload workspace files to sandbox."""
        if not self.needs_upload_sync():
            return
        workspace = self.get_thread_workspace_path(thread_id)
        if not workspace.exists():
            return
        for file_path in workspace.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(workspace)
                remote_path = f"/workspace/files/{relative}"
                content = file_path.read_text()
                provider.write_file(session_id, remote_path, content)
```

**Step 4: Verify test passes**

**Step 5: Commit** → `git add . && git commit -m "feat: implement workspace upload"`

---

## Task 5: Implement Download Sync

**Files:**
- Modify: `sandbox/workspace_sync.py`
- Modify: `tests/sandbox/test_workspace_sync.py`

**Step 1: Write test**

```python
def test_download_workspace_from_sandbox():
    """Should download all files from sandbox to workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_provider = Mock()
        mock_provider.list_dir.return_value = [
            {"name": "file1.txt", "type": "file"},
        ]
        mock_provider.read_file.return_value = "content1"

        sync = WorkspaceSync(
            provider_capability=ProviderCapability(
                can_pause=True, can_resume=True, can_destroy=True,
                mount=MountCapability(supports_mount=False)
            ),
            workspace_root=Path(tmpdir)
        )

        sync.download_workspace("thread-123", "session-456", mock_provider)
        workspace = Path(tmpdir) / "thread-123" / "files"
        assert (workspace / "file1.txt").read_text() == "content1"
```

**Step 2: Implement**

```python
# sandbox/workspace_sync.py
    def download_workspace(self, thread_id: str, session_id: str, provider: SandboxProvider) -> None:
        """Download workspace files from sandbox."""
        if not self.needs_upload_sync():
            return
        workspace = self.get_thread_workspace_path(thread_id)
        workspace.mkdir(parents=True, exist_ok=True)

        def download_recursive(remote_path: str, local_path: Path) -> None:
            items = provider.list_dir(session_id, remote_path)
            for item in items:
                remote_item = f"{remote_path}/{item['name']}".replace("//", "/")
                local_item = local_path / item["name"]
                if item["type"] == "directory":
                    local_item.mkdir(parents=True, exist_ok=True)
                    download_recursive(remote_item, local_item)
                else:
                    content = provider.read_file(session_id, remote_item)
                    local_item.write_text(content)

        download_recursive("/workspace/files", workspace)
```

**Step 3: Commit** → `git add . && git commit -m "feat: implement workspace download"`

---

## Task 6: Integrate into SandboxManager

**Files:**
- Modify: `sandbox/manager.py`

**Step 1: Add WorkspaceSync initialization**

```python
# sandbox/manager.py (in __init__ method)
from sandbox.workspace_sync import WorkspaceSync
from backend.web.core.config import THREAD_FILES_ROOT

    def __init__(self, provider, db_path=None, on_session_ready=None):
        # ... existing code ...
        self.workspace_sync = WorkspaceSync(
            provider_capability=self.provider_capability,
            workspace_root=THREAD_FILES_ROOT
        )
```

**Step 2: Add upload hook after session creation**

```python
# sandbox/manager.py (in get_sandbox method, after session creation)
        session = self.session_manager.create(
            session_id=session_id,
            thread_id=thread_id,
            terminal=terminal,
            lease=lease,
        )

        instance = lease.get_instance()
        if instance:
            # @@@workspace-upload - sync files to sandbox after creation
            try:
                self.workspace_sync.upload_workspace(thread_id, instance.instance_id, self.provider)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to upload workspace: {e}")
            self._fire_session_ready(instance.instance_id, "create")
```

**Step 3: Replace existing download logic in pause_session**

```python
# sandbox/manager.py (replace _sync_workspace_from_sandbox call)
        if lease.observed_state != "paused":
            lease.ensure_active_instance(self.provider)
            instance = lease.get_instance()
            if instance:
                # @@@workspace-download - sync files from sandbox before pause
                try:
                    self.workspace_sync.download_workspace(thread_id, instance.instance_id, self.provider)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Failed to download workspace: {e}")
            if not lease.pause_instance(self.provider):
                return False
```

**Step 4: Add download hook in destroy_thread_resources**

```python
# sandbox/manager.py (at start of destroy_thread_resources, after getting terminals)
    def destroy_thread_resources(self, thread_id: str) -> bool:
        terminals = self.terminal_store.list_by_thread(thread_id)
        if not terminals:
            return False

        # @@@workspace-download - sync files before destroy
        lease = self._get_thread_lease(thread_id)
        if lease:
            instance = lease.get_instance()
            if instance:
                try:
                    self.workspace_sync.download_workspace(thread_id, instance.instance_id, self.provider)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Failed to download workspace: {e}")

        # ... rest of existing code ...
```

**Step 5: Remove old _sync_workspace_from_sandbox method**

Delete the `_sync_workspace_from_sandbox` method that was added earlier.

**Step 6: Commit** → `git add . && git commit -m "feat: integrate workspace sync into manager lifecycle"`

---

## Task 7: Add Error Handling and Logging

**Files:**
- Modify: `sandbox/workspace_sync.py`

**Implementation:**

```python
# sandbox/workspace_sync.py (add at top)
import logging

logger = logging.getLogger(__name__)

# Wrap upload_workspace
    def upload_workspace(self, thread_id: str, session_id: str, provider: SandboxProvider) -> None:
        """Upload workspace files to sandbox."""
        try:
            if not self.needs_upload_sync():
                return
            workspace = self.get_thread_workspace_path(thread_id)
            if not workspace.exists():
                logger.debug(f"No workspace to upload for thread {thread_id}")
                return
            
            file_count = 0
            for file_path in workspace.rglob("*"):
                if file_path.is_file():
                    relative = file_path.relative_to(workspace)
                    remote_path = f"/workspace/files/{relative}"
                    content = file_path.read_text()
                    provider.write_file(session_id, remote_path, content)
                    file_count += 1
            
            logger.info(f"Uploaded {file_count} files to sandbox {session_id}")
        except Exception as e:
            logger.error(f"Failed to upload workspace for thread {thread_id}: {e}")
            raise

# Similar for download_workspace
```

**Commit** → `git add . && git commit -m "feat: add error handling and logging to workspace sync"`

---

## Task 8: Manual Testing

**Test Docker (bind mount):**
1. Start Leon with Docker sandbox
2. Upload a file via UI
3. Send message to agent
4. Verify agent can see file at `/workspace/files/`
5. Agent modifies file
6. Verify changes appear in local workspace immediately

**Test Daytona (upload/download):**
1. Start Leon with Daytona sandbox
2. Upload a file via UI
3. Send message to agent (triggers session creation + upload)
4. Verify agent can see file at `/workspace/files/`
5. Agent creates new file
6. Pause sandbox
7. Verify new file appears in local workspace

**Test file persistence:**
1. Upload file, agent uses it
2. Pause sandbox
3. Resume sandbox
4. Verify file still exists in sandbox

---

## Success Criteria

- [ ] Docker sandboxes use bind mount (no upload/download)
- [ ] Daytona/E2B sandboxes upload files on session creation
- [ ] Daytona/E2B sandboxes download files on pause/destroy
- [ ] Agent receives notification of uploaded files
- [ ] Files persist across sandbox pause/resume cycles
- [ ] All tests pass
- [ ] No errors in logs during normal operation

---

## Rollback Plan

If issues arise:
1. Revert manager.py changes (remove workspace_sync calls)
2. Keep WorkspaceSync class for future use
3. Docker bind mount continues to work
4. Remote providers fall back to no sync (files lost on pause)

