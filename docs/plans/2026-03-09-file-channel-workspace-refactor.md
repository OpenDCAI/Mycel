# File Channel as Workspace Entity

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor file channel to use workspace system properly - file channel becomes a workspace entity with workspace_id, created automatically with thread.

**Architecture:** File channel is a special workspace (auto-created, default) that uses the same abstraction as user workspaces. All operations go through workspace system. Infrastructure doesn't distinguish between file channel and user workspaces - the distinction is at application level only.

**Tech Stack:** Python, FastAPI, SQLite/Supabase, pytest

---

## Current Problems

1. File channel bypasses workspace system (uses default per-thread paths)
2. Workspace entities exist but unused by file channel
3. Sync manager has layering violation (imports from application layer)
4. Path resolution has special cases for "file channel" vs "workspace"

## Desired Architecture

```
Thread Creation → Create file channel workspace entity → Store workspace_id in thread config

File Operations → Use workspace_id (default to file channel) → Workspace system → Path resolution

Sync Operations → Accept workspace_id → Workspace system → Path resolution
```

**Key Principle:** File channel and user workspaces use identical abstraction. Infrastructure doesn't know the difference.

---

### Task 1: Create file channel workspace on thread creation

**Problem:** File channel doesn't exist as workspace entity. Thread creation doesn't create it.

**Files:**
- Modify: `backend/web/routers/threads.py` (thread creation endpoint)
- Modify: `backend/web/services/workspace_service.py` (add helper)

**Step 1: Add helper to create file channel workspace**

Edit `workspace_service.py`:

```python
def create_file_channel_workspace(thread_id: str) -> str:
    """Create file channel workspace for thread. Returns workspace_id."""
    host_path = THREAD_FILES_ROOT / thread_id / "files"
    host_path.mkdir(parents=True, exist_ok=True)
    ws = _create_workspace(str(host_path), name=f"file-channel-{thread_id}")
    return ws["workspace_id"]
```

**Step 2: Call on thread creation**

Edit `threads.py` around line 213 (after thread_id is created):

```python
# Create file channel workspace
from backend.web.services.workspace_service import create_file_channel_workspace
file_channel_workspace_id = await asyncio.to_thread(create_file_channel_workspace, thread_id)

# Store in thread config
if not updates:
    updates = {}
updates["workspace_id"] = file_channel_workspace_id
```

**Step 3: Verify**

Run: `uv run python -m pytest tests/test_file_channel_service.py -v`

**Step 4: Commit**

```bash
git add backend/web/routers/threads.py backend/web/services/workspace_service.py
git commit -m "feat: create file channel workspace on thread creation"
```

---

### Task 2: Update workspace_service to accept workspace_id

**Problem:** File operations (_get_files_dir, save_file, etc.) don't accept workspace_id parameter. They only use thread_id.

**Files:**
- Modify: `backend/web/services/workspace_service.py`

**Step 1: Update _get_files_dir to accept workspace_id**

```python
def _get_files_dir(thread_id: str, workspace_id: str | None = None) -> Path:
    """Derive files directory. If workspace_id not provided, use thread's file channel workspace."""
    if not workspace_id:
        workspace_id = _get_workspace_id(thread_id)
    if not workspace_id:
        raise ValueError(f"No workspace found for thread {thread_id}")

    ws = _get_workspace(workspace_id)
    if not ws:
        raise ValueError(f"Workspace not found: {workspace_id}")

    d = Path(ws["host_path"]).resolve()
    if not d.is_dir():
        raise ValueError(f"Workspace directory missing: {d}")
    return d
```

**Step 2: Update save_file, resolve_file, list_files**

Add `workspace_id: str | None = None` parameter to each:

```python
def save_file(
    *,
    thread_id: str,
    relative_path: str,
    content: bytes,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    base = _get_files_dir(thread_id, workspace_id)
    # ... rest unchanged
```

Same for `resolve_file` and `list_files`.

**Step 3: Verify**

Run: `uv run python -m pytest tests/test_file_channel_service.py -v`

**Step 4: Commit**

```bash
git add backend/web/services/workspace_service.py
git commit -m "feat: workspace_service accepts workspace_id parameter"
```

---

### Task 3: Update file channel endpoints to accept workspace_id

**Problem:** Upload/download endpoints don't accept workspace_id parameter.

**Files:**
- Modify: `backend/web/routers/thread_workspace.py`

**Step 1: Add workspace_id parameter to endpoints**

```python
@router.post("/upload")
async def upload_workspace_file(
    thread_id: str,
    file: UploadFile = File(...),
    path: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),  # ← Add this
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    # ...
    payload = await asyncio.to_thread(
        save_file,
        thread_id=thread_id,
        relative_path=relative_path,
        content=content,
        workspace_id=workspace_id,  # ← Pass through
    )
```

Same for `/download` and `/channel-files` endpoints.

**Step 2: Verify**

Run: `uv run python -m pytest tests/test_file_channel_service.py -v`

**Step 3: Commit**

```bash
git add backend/web/routers/thread_workspace.py
git commit -m "feat: file channel endpoints accept workspace_id parameter"
```

---

### Task 4: Fix sync manager layering violation

**Problem:** Sync manager imports from application layer (backend.web.utils.helpers).

**Files:**
- Modify: `sandbox/sync/manager.py`
- Modify: `sandbox/sync/strategy.py`

**Step 1: Remove workspace resolution from sync manager**

The sync manager should NOT resolve workspace paths. The caller should resolve and pass the path.

Edit `sandbox/sync/manager.py` - revert to simple implementation:

```python
def get_thread_workspace_path(self, thread_id: str) -> Path:
    """Get default per-thread path."""
    return self.workspace_root / thread_id / "files"
```

Remove the workspace_id lookup logic.

**Step 2: Update strategy to use simple path**

Edit `sandbox/sync/strategy.py` - revert to simple implementation:

```python
def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
    workspace = self.manager.get_thread_workspace_path(thread_id) if self.manager else self.workspace_root / thread_id / "files"
```

**Step 3: Verify**

Run: `uv run python -m pytest tests/test_sync_strategy.py -v`

**Step 4: Commit**

```bash
git add sandbox/sync/manager.py sandbox/sync/strategy.py
git commit -m "fix: remove sync manager layering violation"
```

---

### Task 5: Update tests

**Problem:** Tests need to verify file channel workspace creation and usage.

**Files:**
- Modify: `tests/test_file_channel_service.py`

**Step 1: Add test for file channel workspace creation**

```python
def test_file_channel_workspace_created_on_thread_creation():
    """Thread creation should create file channel workspace."""
    from backend.web.services.workspace_service import create_file_channel_workspace, _get_workspace
    
    thread_id = "test-thread-123"
    workspace_id = create_file_channel_workspace(thread_id)
    
    # Verify workspace exists
    ws = _get_workspace(workspace_id)
    assert ws is not None
    assert "file-channel" in ws["name"]
    assert str(Path.home() / ".leon" / "thread_files" / thread_id / "files") in ws["host_path"]
```

**Step 2: Update existing tests to use workspace_id**

Modify tests to pass workspace_id parameter where applicable.

**Step 3: Verify all tests pass**

Run: `uv run python -m pytest tests/ -v`

**Step 4: Commit**

```bash
git add tests/
git commit -m "test: verify file channel workspace creation and usage"
```

---

## Verification

After all tasks complete:

```bash
# All tests should pass
uv run python -m pytest tests/test_file_channel_service.py tests/test_sync_strategy.py -v

# YATU test - create thread, upload file, verify workspace entity exists
curl -X POST http://localhost:8003/api/threads -H "Content-Type: application/json" -d '{"sandbox":"local"}'
# Extract thread_id from response
# Upload file
# Verify workspace entity in database
```

## Summary

This refactoring makes file channel a proper workspace entity:
- ✅ File channel has workspace_id (created on thread creation)
- ✅ File operations use workspace system (same as user workspaces)
- ✅ Infrastructure doesn't distinguish file channel vs user workspace
- ✅ Sync manager has no layering violations
- ✅ Path resolution is simple (workspace_id → workspace entity → host_path)

---

## YATU Testing

After implementation, test as the user with real API calls.

### Test Script

Create `/tmp/yatu-file-channel-workspace.sh`:

```bash
#!/bin/bash
set -e

echo "=== YATU: File Channel as Workspace Entity ==="

# 1. Create thread
echo -e "\n1. Creating thread..."
RESPONSE=$(curl -s -X POST http://localhost:8003/api/threads \
  -H "Content-Type: application/json" \
  -d '{"sandbox":"local"}')
THREAD_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['thread_id'])")
echo "Thread created: $THREAD_ID"

# 2. Verify file channel workspace was created
echo -e "\n2. Checking if file channel workspace exists..."
WORKSPACE_ID=$(sqlite3 ~/.leon/leon.db \
  "SELECT workspace_id FROM thread_config WHERE thread_id='$THREAD_ID'" 2>/dev/null || echo "")
if [ -z "$WORKSPACE_ID" ]; then
  echo "❌ FAIL: No workspace_id in thread config"
  exit 1
fi
echo "✓ File channel workspace_id: $WORKSPACE_ID"

# 3. Verify workspace entity exists
echo -e "\n3. Verifying workspace entity..."
WS_PATH=$(sqlite3 ~/.leon/leon.db \
  "SELECT host_path FROM workspaces WHERE workspace_id='$WORKSPACE_ID'" 2>/dev/null || echo "")
if [ -z "$WS_PATH" ]; then
  echo "❌ FAIL: Workspace entity not found"
  exit 1
fi
echo "✓ Workspace path: $WS_PATH"

# 4. Upload file (should use file channel workspace by default)
echo -e "\n4. Uploading file to file channel..."
echo "Test content from YATU" > /tmp/yatu-test-file.txt
UPLOAD_RESPONSE=$(curl -s -X POST \
  "http://localhost:8003/api/threads/$THREAD_ID/workspace/upload" \
  -F "file=@/tmp/yatu-test-file.txt")
echo "$UPLOAD_RESPONSE" | python3 -m json.tool

# 5. Verify file exists at workspace path
echo -e "\n5. Verifying file exists at workspace path..."
if [ ! -f "$WS_PATH/yatu-test-file.txt" ]; then
  echo "❌ FAIL: File not found at workspace path"
  exit 1
fi
CONTENT=$(cat "$WS_PATH/yatu-test-file.txt")
if [ "$CONTENT" != "Test content from YATU" ]; then
  echo "❌ FAIL: File content mismatch"
  exit 1
fi
echo "✓ File exists at workspace path with correct content"

# 6. Download file
echo -e "\n6. Downloading file..."
curl -s "http://localhost:8003/api/threads/$THREAD_ID/workspace/download?path=yatu-test-file.txt" \
  -o /tmp/yatu-downloaded.txt
DOWNLOADED=$(cat /tmp/yatu-downloaded.txt)
if [ "$DOWNLOADED" != "Test content from YATU" ]; then
  echo "❌ FAIL: Downloaded content mismatch"
  exit 1
fi
echo "✓ File downloaded successfully"

# 7. List files
echo -e "\n7. Listing files..."
curl -s "http://localhost:8003/api/threads/$THREAD_ID/workspace/channel-files" | python3 -m json.tool

echo -e "\n=== ✓ All YATU Tests Passed ==="
```

### Run YATU Test

```bash
chmod +x /tmp/yatu-file-channel-workspace.sh
/tmp/yatu-file-channel-workspace.sh
```

### Expected Output

```
=== YATU: File Channel as Workspace Entity ===

1. Creating thread...
Thread created: <uuid>

2. Checking if file channel workspace exists...
✓ File channel workspace_id: <uuid>

3. Verifying workspace entity...
✓ Workspace path: /Users/<user>/.leon/thread_files/<thread_id>/files

4. Uploading file to file channel...
{
  "thread_id": "<uuid>",
  "relative_path": "yatu-test-file.txt",
  "absolute_path": "/Users/<user>/.leon/thread_files/<thread_id>/files/yatu-test-file.txt",
  "size_bytes": 23,
  "sha256": "<hash>"
}

5. Verifying file exists at workspace path...
✓ File exists at workspace path with correct content

6. Downloading file...
✓ File downloaded successfully

7. Listing files...
{
  "thread_id": "<uuid>",
  "entries": [
    {
      "relative_path": "yatu-test-file.txt",
      "size_bytes": 23,
      "updated_at": "<timestamp>"
    }
  ]
}

=== ✓ All YATU Tests Passed ===
```

### What YATU Verifies

- ✅ Thread creation creates file channel workspace entity
- ✅ workspace_id stored in thread config
- ✅ Workspace entity exists in database with correct path
- ✅ File upload uses workspace system
- ✅ Files stored at workspace path (not bypassing workspace system)
- ✅ File download works through workspace system
- ✅ File listing works through workspace system

If any step fails, the refactoring is incomplete.
