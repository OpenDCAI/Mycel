# Workspace Sync Manager Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a robust workspace sync manager with optimization strategies, change detection, and provider-specific configuration for efficient file synchronization between local workspace and remote sandboxes.

**Architecture:** Strategy pattern with SyncManager orchestrating different sync strategies (Full, Incremental, SingleFile). State tracking via SyncState to detect changes. Provider-specific configuration for paths and capabilities. Error handling with retry logic and partial failure recovery.

**Tech Stack:** Python 3.12, Pydantic for models, Leon's SQLite kernel (SANDBOX role) for state tracking, hashlib for checksums

---

## Task 1: Design SyncManager Architecture

**Files:**
- Create: `sandbox/sync/manager.py`
- Create: `sandbox/sync/strategy.py`
- Create: `sandbox/sync/state.py`
- Create: `sandbox/sync/__init__.py`

**Step 1: Write test for SyncManager initialization**

```python
# tests/sandbox/sync/test_manager.py
def test_sync_manager_initialization():
    from sandbox.sync.manager import SyncManager
    from sandbox.provider import ProviderCapability
    from pathlib import Path

    capability = ProviderCapability(runtime_kind="docker")
    workspace_root = Path("/tmp/test")

    manager = SyncManager(capability, workspace_root)

    assert manager.provider_capability == capability
    assert manager.workspace_root == workspace_root
    assert manager.strategy is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/sandbox/sync/test_manager.py::test_sync_manager_initialization -v`
Expected: FAIL with "No module named 'sandbox.sync'"

**Step 3: Create SyncManager skeleton**

```python
# sandbox/sync/manager.py
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sandbox.provider import ProviderCapability, SandboxProvider
    from sandbox.sync.strategy import SyncStrategy

class SyncManager:
    def __init__(self, provider_capability: ProviderCapability, workspace_root: Path):
        self.provider_capability = provider_capability
        self.workspace_root = workspace_root
        self.strategy = self._select_strategy()

    def _select_strategy(self) -> SyncStrategy:
        from sandbox.sync.strategy import NoOpStrategy
        return NoOpStrategy()
```

**Step 4: Create strategy interface**

```python
# sandbox/sync/strategy.py
from abc import ABC, abstractmethod

class SyncStrategy(ABC):
    @abstractmethod
    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        pass

    @abstractmethod
    def download(self, thread_id: str, session_id: str, provider):
        pass

class NoOpStrategy(SyncStrategy):
    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        pass

    def download(self, thread_id: str, session_id: str, provider):
        pass
```

**Step 5: Create __init__.py**

```python
# sandbox/sync/__init__.py
from sandbox.sync.manager import SyncManager

__all__ = ["SyncManager"]
```

**Step 6: Run test to verify it passes**

Run: `pytest tests/sandbox/sync/test_manager.py::test_sync_manager_initialization -v`
Expected: PASS

**Step 7: Commit**

```bash
git add sandbox/sync/ tests/sandbox/sync/
git commit -m "feat: add SyncManager architecture skeleton"
```

---

## Task 2: Implement State Tracking

**Files:**
- Create: `sandbox/sync/state.py`
- Create: `tests/sandbox/sync/test_state.py`

**Step 1: Write test for SyncState**

```python
# tests/sandbox/sync/test_state.py
def test_sync_state_track_file():
    from sandbox.sync.state import SyncState

    state = SyncState()

    state.track_file("thread1", "file.txt", "abc123", 1234567890)

    info = state.get_file_info("thread1", "file.txt")
    assert info["checksum"] == "abc123"
    assert info["last_synced"] == 1234567890
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/sandbox/sync/test_state.py::test_sync_state_track_file -v`
Expected: FAIL with "No module named 'sandbox.sync.state'"

**Step 3: Implement SyncState**

```python
# sandbox/sync/state.py
from storage.providers.sqlite.kernel import connect_sqlite_role, SQLiteDBRole

class SyncState:
    def __init__(self):
        self._ensure_tables()

    def _ensure_tables(self):
        with connect_sqlite_role(SQLiteDBRole.SANDBOX) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_files (
                    thread_id TEXT,
                    relative_path TEXT,
                    checksum TEXT,
                    last_synced INTEGER,
                    PRIMARY KEY (thread_id, relative_path)
                )
            """)

    def track_file(self, thread_id: str, relative_path: str, checksum: str, timestamp: int):
        with connect_sqlite_role(SQLiteDBRole.SANDBOX) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sync_files VALUES (?, ?, ?, ?)",
                (thread_id, relative_path, checksum, timestamp)
            )

    def get_file_info(self, thread_id: str, relative_path: str) -> dict | None:
        with connect_sqlite_role(SQLiteDBRole.SANDBOX) as conn:
            row = conn.execute(
                "SELECT checksum, last_synced FROM sync_files WHERE thread_id = ? AND relative_path = ?",
                (thread_id, relative_path)
            ).fetchone()
            if row:
                return {"checksum": row[0], "last_synced": row[1]}
            return None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/sandbox/sync/test_state.py::test_sync_state_track_file -v`
Expected: PASS

**Step 5: Commit**

```bash
git add sandbox/sync/state.py tests/sandbox/sync/test_state.py
git commit -m "feat: add SyncState for tracking synced files"
```

---

## Task 3: Implement Change Detection

**Files:**
- Modify: `sandbox/sync/state.py`
- Create: `tests/sandbox/sync/test_change_detection.py`

**Step 1: Write test for change detection**

```python
# tests/sandbox/sync/test_change_detection.py
def test_detect_changed_files():
    from sandbox.sync.state import SyncState
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()

        state = SyncState()

        # Create file and track it
        file1 = workspace / "file1.txt"
        file1.write_text("content1")
        state.track_file("thread1", "file1.txt", "hash1", 1000)

        # Modify file
        file1.write_text("content2")

        # Detect changes
        changed = state.detect_changes("thread1", workspace)
        assert "file1.txt" in changed
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/sandbox/sync/test_change_detection.py::test_detect_changed_files -v`
Expected: FAIL with "SyncState has no method detect_changes"

**Step 3: Add checksum calculation**

```python
# sandbox/sync/state.py
import hashlib

def _calculate_checksum(file_path: Path) -> str:
    """Calculate SHA256 checksum of file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()
```

**Step 4: Add change detection method**

```python
# sandbox/sync/state.py (add to SyncState class)
def detect_changes(self, thread_id: str, workspace_path: Path) -> list[str]:
    """Detect files that changed since last sync."""
    changed = []
    for file_path in workspace_path.rglob("*"):
        if file_path.is_file():
            relative = str(file_path.relative_to(workspace_path))
            current_checksum = _calculate_checksum(file_path)
            info = self.get_file_info(thread_id, relative)
            if not info or info["checksum"] != current_checksum:
                changed.append(relative)
    return changed
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/sandbox/sync/test_change_detection.py::test_detect_changed_files -v`
Expected: PASS

**Step 6: Commit**

```bash
git add sandbox/sync/state.py tests/sandbox/sync/test_change_detection.py
git commit -m "feat: add change detection with checksums"
```

---

## Task 4: Implement Full Sync Strategy

**Files:**
- Modify: `sandbox/sync/strategy.py`
- Create: `tests/sandbox/sync/test_full_sync.py`

**Step 1: Write test for full sync**

```python
# tests/sandbox/sync/test_full_sync.py
def test_full_sync_upload():
    from sandbox.sync.strategy import FullSyncStrategy
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "file1.txt").write_text("content1")
        (workspace / "file2.txt").write_text("content2")

        provider = MockProvider()
        strategy = FullSyncStrategy(workspace)

        strategy.upload("thread1", "session1", provider)

        assert len(provider.uploaded) == 2
        assert "file1.txt" in provider.uploaded
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/sandbox/sync/test_full_sync.py::test_full_sync_upload -v`
Expected: FAIL with "No class FullSyncStrategy"

**Step 3: Implement FullSyncStrategy**

```python
# sandbox/sync/strategy.py
class FullSyncStrategy(SyncStrategy):
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        workspace = self.workspace_root / thread_id / "files"
        if not workspace.exists():
            return

        for file_path in workspace.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(workspace)
                remote_path = f"/workspace/files/{relative}"
                content = file_path.read_text()
                provider.write_file(session_id, remote_path, content)

    def download(self, thread_id: str, session_id: str, provider):
        workspace = self.workspace_root / thread_id / "files"
        workspace.mkdir(parents=True, exist_ok=True)

        def download_recursive(remote_path: str, local_path: Path):
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

**Step 4: Run test to verify it passes**

Run: `pytest tests/sandbox/sync/test_full_sync.py::test_full_sync_upload -v`
Expected: PASS

**Step 5: Commit**

```bash
git add sandbox/sync/strategy.py tests/sandbox/sync/test_full_sync.py
git commit -m "feat: add FullSyncStrategy"
```

---

## Task 5: Implement Incremental Sync Strategy

**Files:**
- Modify: `sandbox/sync/strategy.py`
- Create: `tests/sandbox/sync/test_incremental_sync.py`

**Step 1: Write test for incremental sync**

```python
# tests/sandbox/sync/test_incremental_sync.py
def test_incremental_sync_only_changed():
    from sandbox.sync.strategy import IncrementalSyncStrategy
    from sandbox.sync.state import SyncState
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()

        state = SyncState()
        provider = MockProvider()
        strategy = IncrementalSyncStrategy(Path(tmpdir), state)

        # First sync
        (workspace / "file1.txt").write_text("content1")
        strategy.upload("thread1", "session1", provider)
        assert len(provider.uploaded) == 1

        # Second sync - no changes
        provider.uploaded.clear()
        strategy.upload("thread1", "session1", provider)
        assert len(provider.uploaded) == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/sandbox/sync/test_incremental_sync.py::test_incremental_sync_only_changed -v`
Expected: FAIL with "No class IncrementalSyncStrategy"

**Step 3: Implement IncrementalSyncStrategy**

```python
# sandbox/sync/strategy.py
import time

class IncrementalSyncStrategy(SyncStrategy):
    def __init__(self, workspace_root: Path, state: SyncState):
        self.workspace_root = workspace_root
        self.state = state

    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        workspace = self.workspace_root / thread_id / "files"
        if not workspace.exists():
            return

        if files:
            # Upload specific files
            to_upload = files
        else:
            # Detect changed files
            to_upload = self.state.detect_changes(thread_id, workspace)

        for relative_path in to_upload:
            file_path = workspace / relative_path
            if file_path.exists():
                remote_path = f"/workspace/files/{relative_path}"
                content = file_path.read_text()
                provider.write_file(session_id, remote_path, content)

                # Track synced file
                from sandbox.sync.state import _calculate_checksum
                checksum = _calculate_checksum(file_path)
                self.state.track_file(thread_id, relative_path, checksum, int(time.time()))

    def download(self, thread_id: str, session_id: str, provider):
        # Same as FullSyncStrategy for now
        workspace = self.workspace_root / thread_id / "files"
        workspace.mkdir(parents=True, exist_ok=True)

        def download_recursive(remote_path: str, local_path: Path):
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

**Step 4: Run test to verify it passes**

Run: `pytest tests/sandbox/sync/test_incremental_sync.py::test_incremental_sync_only_changed -v`
Expected: PASS

**Step 5: Commit**

```bash
git add sandbox/sync/strategy.py tests/sandbox/sync/test_incremental_sync.py
git commit -m "feat: add IncrementalSyncStrategy with change detection"
```

---

## Task 6: Implement Strategy Selection Logic

**Files:**
- Modify: `sandbox/sync/manager.py`
- Create: `tests/sandbox/sync/test_strategy_selection.py`

**Step 1: Write test for strategy selection**

```python
# tests/sandbox/sync/test_strategy_selection.py
def test_select_strategy_for_docker():
    from sandbox.sync.manager import SyncManager
    from sandbox.sync.strategy import NoOpStrategy
    from sandbox.provider import ProviderCapability
    from pathlib import Path

    capability = ProviderCapability(runtime_kind="docker")
    manager = SyncManager(capability, Path("/tmp"))

    assert isinstance(manager.strategy, NoOpStrategy)

def test_select_strategy_for_daytona():
    from sandbox.sync.manager import SyncManager
    from sandbox.sync.strategy import IncrementalSyncStrategy
    from sandbox.provider import ProviderCapability
    from pathlib import Path

    capability = ProviderCapability(runtime_kind="daytona")
    manager = SyncManager(capability, Path("/tmp"))

    assert isinstance(manager.strategy, IncrementalSyncStrategy)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/sandbox/sync/test_strategy_selection.py -v`
Expected: FAIL with assertion errors

**Step 3: Update strategy selection logic**

```python
# sandbox/sync/manager.py
def _select_strategy(self) -> SyncStrategy:
    from sandbox.sync.strategy import NoOpStrategy, IncrementalSyncStrategy
    from sandbox.sync.state import SyncState

    runtime_kind = self.provider_capability.runtime_kind

    # Docker and local use bind mounts - no sync needed
    if runtime_kind in ("local", "docker"):
        return NoOpStrategy()

    # Remote providers use incremental sync
    state = SyncState()
    return IncrementalSyncStrategy(self.workspace_root, state)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/sandbox/sync/test_strategy_selection.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add sandbox/sync/manager.py tests/sandbox/sync/test_strategy_selection.py
git commit -m "feat: add strategy selection based on runtime kind"
```

---

## Task 7: Integrate SyncManager with Existing Code

**Files:**
- Modify: `sandbox/manager.py`
- Modify: `backend/web/routers/workspace.py`

**Step 1: Replace WorkspaceSync with SyncManager in sandbox/manager.py**

```python
# sandbox/manager.py (in __init__)
from sandbox.sync.manager import SyncManager

self.workspace_sync = SyncManager(
    provider_capability=self.provider.get_capability(),
    workspace_root=workspace_root,
)
```

**Step 2: Update upload call in workspace.py**

```python
# backend/web/routers/workspace.py (in upload_workspace_file)
if manager and manager.workspace_sync.strategy.needs_upload_sync():
    try:
        session = manager.session_manager.get_by_thread(thread_id)
        if session:
            # Use strategy to upload single file
            await asyncio.to_thread(
                manager.workspace_sync.strategy.upload,
                thread_id, session.session_id, manager.provider, [relative_path]
            )
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to sync uploaded file: {e}")
```

**Step 3: Add needs_upload_sync to SyncManager**

```python
# sandbox/sync/manager.py
def needs_upload_sync(self) -> bool:
    """Check if provider needs explicit upload sync."""
    return self.provider_capability.runtime_kind not in ("local", "docker")

def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
    """Delegate to strategy."""
    self.strategy.upload(thread_id, session_id, provider, files)

def download(self, thread_id: str, session_id: str, provider):
    """Delegate to strategy."""
    self.strategy.download(thread_id, session_id, provider)
```

**Step 4: Run integration test**

Run: `pytest tests/sandbox/sync/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add sandbox/manager.py backend/web/routers/workspace.py sandbox/sync/manager.py
git commit -m "feat: integrate SyncManager with existing code"
```

---

## Task 8: Add Error Handling and Retry Logic

**Files:**
- Create: `sandbox/sync/retry.py`
- Modify: `sandbox/sync/strategy.py`
- Create: `tests/sandbox/sync/test_retry.py`

**Step 1: Write test for retry logic**

```python
# tests/sandbox/sync/test_retry.py
def test_retry_on_failure():
    from sandbox.sync.retry import retry_with_backoff

    call_count = 0

    @retry_with_backoff(max_retries=3, backoff_factor=0.1)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Temporary failure")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/sandbox/sync/test_retry.py::test_retry_on_failure -v`
Expected: FAIL with "No module named 'sandbox.sync.retry'"

**Step 3: Implement retry decorator**

```python
# sandbox/sync/retry.py
import time
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries=3, backoff_factor=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    wait_time = backoff_factor ** attempt
                    logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
        return wrapper
    return decorator
```

**Step 4: Add retry to strategy methods**

```python
# sandbox/sync/strategy.py
from sandbox.sync.retry import retry_with_backoff

class IncrementalSyncStrategy(SyncStrategy):
    @retry_with_backoff(max_retries=3, backoff_factor=1)
    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        # existing implementation
        pass
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/sandbox/sync/test_retry.py::test_retry_on_failure -v`
Expected: PASS

**Step 6: Commit**

```bash
git add sandbox/sync/retry.py sandbox/sync/strategy.py tests/sandbox/sync/test_retry.py
git commit -m "feat: add retry logic with exponential backoff"
```

---

## Task 9: End-to-End Testing

**Files:**
- Create: `tests/sandbox/sync/test_e2e.py`

**Step 1: Write end-to-end test**

```python
# tests/sandbox/sync/test_e2e.py
def test_e2e_file_upload_sync():
    from sandbox.sync.manager import SyncManager
    from sandbox.provider import ProviderCapability
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_root = Path(tmpdir)
        capability = ProviderCapability(runtime_kind="daytona")
        manager = SyncManager(capability, workspace_root)

        # Simulate file upload
        thread_id = "test-thread"
        workspace = workspace_root / thread_id / "files"
        workspace.mkdir(parents=True)
        (workspace / "uploaded.txt").write_text("test content")

        # Mock provider
        provider = MockProvider()
        session_id = "test-session"

        # Upload single file
        manager.upload(thread_id, session_id, provider, ["uploaded.txt"])

        # Verify file was uploaded
        assert "uploaded.txt" in provider.uploaded
        assert provider.uploaded["uploaded.txt"] == "test content"
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/sandbox/sync/test_e2e.py::test_e2e_file_upload_sync -v`
Expected: PASS

**Step 3: Run all sync tests**

Run: `pytest tests/sandbox/sync/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/sandbox/sync/test_e2e.py
git commit -m "test: add end-to-end sync tests"
```

---

## Summary

This plan implements a robust workspace sync manager with:

1. **Strategy Pattern**: NoOpStrategy for Docker/local, IncrementalSyncStrategy for remote providers
2. **State Tracking**: Leon's SQLite kernel (SANDBOX role) for tracking with checksums for change detection
3. **Optimization**: Only sync changed files, not full workspace on every upload
4. **Error Handling**: Retry logic with exponential backoff for transient failures
5. **Provider-Specific**: Automatic strategy selection based on runtime_kind

**Key Benefits**:
- Eliminates full workspace sync on every file upload
- Tracks file state to detect changes efficiently
- Handles network failures gracefully with retries
- Clean abstraction separating sync logic from provider logic
- Uses Leon's database abstraction layer (no raw SQLite)

**Refactoring Note**:
- If any abstraction leak is found during implementation (e.g., direct database access, provider-specific logic in generic code), refactor immediately to maintain clean separation of concerns

**Next Steps After Implementation**:
- Remove old `sandbox/workspace_sync.py` file
- Update documentation
- Monitor sync performance in production
