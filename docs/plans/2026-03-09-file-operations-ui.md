# File Operations UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add file download/delete operations with three-dots menu UI in file browser.

**Architecture:** Three-layer implementation: backbone (workspace_service), application (REST API), frontend (React UI). File operations are workspace-level, not sandbox-level. Client-side confirmation prevents accidental deletion.

**Tech Stack:** Python, FastAPI, React, TypeScript, shadcn/ui

---

## Task 1: Add delete_file() to Workspace Service

**Files:**
- Modify: `backend/web/services/workspace_service.py`
- Test: `tests/test_file_channel_service.py`

**Step 1: Write the failing test**

Add to `tests/test_file_channel_service.py`:

```python
def test_delete_file(_patch_services) -> None:
    import backend.web.services.workspace_service as svc

    _save_thread_config("thread-delete")
    svc.ensure_thread_files("thread-delete")
    svc.save_file(thread_id="thread-delete", relative_path="to_delete.txt", content=b"data")

    svc.delete_file(thread_id="thread-delete", relative_path="to_delete.txt")

    with pytest.raises(FileNotFoundError):
        svc.resolve_file(thread_id="thread-delete", relative_path="to_delete.txt")


def test_delete_file_not_found(_patch_services) -> None:
    import backend.web.services.workspace_service as svc

    _save_thread_config("thread-delete-2")
    svc.ensure_thread_files("thread-delete-2")

    with pytest.raises(FileNotFoundError):
        svc.delete_file(thread_id="thread-delete-2", relative_path="nonexistent.txt")
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_file_channel_service.py::test_delete_file -v`
Expected: FAIL with "AttributeError: module has no attribute 'delete_file'"

**Step 3: Implement delete_file()**

Add to `backend/web/services/workspace_service.py` after `list_files()`:

```python
def delete_file(
    *,
    thread_id: str,
    relative_path: str,
    workspace_id: str | None = None,
) -> None:
    """Delete a file from workspace."""
    base = _get_files_dir(thread_id, workspace_id)
    target = _resolve_relative_path(base, relative_path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File not found: {relative_path}")
    target.unlink()
```

**Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_file_channel_service.py::test_delete_file tests/test_file_channel_service.py::test_delete_file_not_found -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/web/services/workspace_service.py tests/test_file_channel_service.py
git commit -m "feat: add delete_file() to workspace service"
```

---

## Task 2: Add DELETE Endpoint

**Files:**
- Modify: `backend/web/routers/thread_workspace.py`

**Step 1: Add DELETE endpoint**

Add after the download endpoint (around line 209):

```python
@router.delete("/files")
async def delete_workspace_file(
    thread_id: str,
    path: str = Query(...),
    workspace_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Delete a file from workspace."""
    from backend.web.services.workspace_service import delete_file

    try:
        await asyncio.to_thread(
            delete_file,
            thread_id=thread_id,
            relative_path=path,
            workspace_id=workspace_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "path": path}
```

**Step 2: Test endpoint manually**

Start backend, then:
```bash
# Create thread and upload file
THREAD_ID=$(curl -s -X POST http://127.0.0.1:8003/api/threads -H "Content-Type: application/json" -d '{"sandbox": "local"}' | python3 -c "import sys, json; print(json.load(sys.stdin)['thread_id'])")

echo "test" > /tmp/test.txt
curl -X POST "http://127.0.0.1:8003/api/threads/$THREAD_ID/workspace/upload?path=test.txt" -F "file=@/tmp/test.txt"

# Delete file
curl -X DELETE "http://127.0.0.1:8003/api/threads/$THREAD_ID/workspace/files?path=test.txt"

# Verify deleted (should return 404)
curl -X GET "http://127.0.0.1:8003/api/threads/$THREAD_ID/workspace/download?path=test.txt"
```

Expected: Delete returns `{"ok": true, "path": "test.txt"}`, download returns 404

**Step 3: Commit**

```bash
git add backend/web/routers/thread_workspace.py
git commit -m "feat: add DELETE endpoint for file deletion"
```

---

## Task 3: Create File Browser Component

**Files:**
- Create: `frontend/app/src/components/FileBrowser.tsx`
- Create: `frontend/app/src/hooks/useFileList.ts`

**Step 1: Create useFileList hook**

Create `frontend/app/src/hooks/useFileList.ts`:

```typescript
import { useState, useEffect } from 'react';

interface FileEntry {
  relative_path: string;
  size_bytes: number;
  updated_at: string;
}

export function useFileList(threadId: string | undefined) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFiles = async () => {
    if (!threadId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/threads/${threadId}/workspace/channel-files`);
      if (!res.ok) throw new Error('Failed to fetch files');
      const data = await res.json();
      setFiles(data.entries || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, [threadId]);

  return { files, loading, error, refetch: fetchFiles };
}
```

**Step 2: Create FileBrowser component**

Create `frontend/app/src/components/FileBrowser.tsx`:

```typescript
import { useFileList } from '@/hooks/useFileList';

interface FileBrowserProps {
  threadId: string;
}

export function FileBrowser({ threadId }: FileBrowserProps) {
  const { files, loading, error } = useFileList(threadId);

  if (loading) return <div>Loading files...</div>;
  if (error) return <div>Error: {error}</div>;
  if (files.length === 0) return <div>No files uploaded</div>;

  return (
    <div className="space-y-2">
      {files.map((file) => (
        <div key={file.relative_path} className="flex items-center justify-between p-2 border rounded">
          <span>{file.relative_path}</span>
          <span className="text-sm text-gray-500">{(file.size_bytes / 1024).toFixed(1)} KB</span>
        </div>
      ))}
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add frontend/app/src/components/FileBrowser.tsx frontend/app/src/hooks/useFileList.ts
git commit -m "feat: add file browser component"
```

---

## Task 4: Add Three-Dots Menu with Dropdown

**Files:**
- Modify: `frontend/app/src/components/FileBrowser.tsx`

**Step 1: Install/verify shadcn dropdown menu**

Check if dropdown menu component exists:
```bash
cd frontend/app && ls src/components/ui/dropdown-menu.tsx
```

If not exists, add it:
```bash
npx shadcn-ui@latest add dropdown-menu
```

**Step 2: Add three-dots menu to FileBrowser**

Update `frontend/app/src/components/FileBrowser.tsx`:

```typescript
import { useFileList } from '@/hooks/useFileList';
import { MoreVertical } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';

interface FileBrowserProps {
  threadId: string;
}

export function FileBrowser({ threadId }: FileBrowserProps) {
  const { files, loading, error } = useFileList(threadId);

  if (loading) return <div>Loading files...</div>;
  if (error) return <div>Error: {error}</div>;
  if (files.length === 0) return <div>No files uploaded</div>;

  return (
    <div className="space-y-2">
      {files.map((file) => (
        <div key={file.relative_path} className="flex items-center justify-between p-2 border rounded">
          <span>{file.relative_path}</span>
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">{(file.size_bytes / 1024).toFixed(1)} KB</span>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem>Download</DropdownMenuItem>
                <DropdownMenuItem className="text-red-600">Delete</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      ))}
    </div>
  );
}
```

**Step 3: Test UI**

Verify three-dots button appears and dropdown opens with Download/Delete options.

**Step 4: Commit**

```bash
git add frontend/app/src/components/FileBrowser.tsx
git commit -m "feat: add three-dots menu to file browser"
```

---

## Task 5: Implement Download Action

**Files:**
- Modify: `frontend/app/src/components/FileBrowser.tsx`

**Step 1: Add download handler**

Update `FileBrowser.tsx`:

```typescript
export function FileBrowser({ threadId }: FileBrowserProps) {
  const { files, loading, error } = useFileList(threadId);

  const handleDownload = (path: string) => {
    const url = `/api/threads/${threadId}/workspace/download?path=${encodeURIComponent(path)}`;
    window.open(url, '_blank');
  };

  // ... rest of component

  return (
    <div className="space-y-2">
      {files.map((file) => (
        <div key={file.relative_path} className="flex items-center justify-between p-2 border rounded">
          <span>{file.relative_path}</span>
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">{(file.size_bytes / 1024).toFixed(1)} KB</span>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => handleDownload(file.relative_path)}>
                  Download
                </DropdownMenuItem>
                <DropdownMenuItem className="text-red-600">Delete</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      ))}
    </div>
  );
}
```

**Step 2: Test download**

Upload a file, click three-dots → Download, verify browser downloads the file.

**Step 3: Commit**

```bash
git add frontend/app/src/components/FileBrowser.tsx
git commit -m "feat: implement file download action"
```

---

## Task 6: Implement Delete Action with Confirmation

**Files:**
- Modify: `frontend/app/src/components/FileBrowser.tsx`

**Step 1: Install/verify alert dialog**

```bash
cd frontend/app && npx shadcn-ui@latest add alert-dialog
```

**Step 2: Add delete handler with confirmation**

Update `FileBrowser.tsx`:

```typescript
import { useState } from 'react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

export function FileBrowser({ threadId }: FileBrowserProps) {
  const { files, loading, error, refetch } = useFileList(threadId);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const handleDownload = (path: string) => {
    const url = `/api/threads/${threadId}/workspace/download?path=${encodeURIComponent(path)}`;
    window.open(url, '_blank');
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await fetch(
        `/api/threads/${threadId}/workspace/files?path=${encodeURIComponent(deleteTarget)}`,
        { method: 'DELETE' }
      );
      if (!res.ok) throw new Error('Failed to delete file');
      await refetch();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to delete file');
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  };

  // ... rest of component

  return (
    <>
      <div className="space-y-2">
        {files.map((file) => (
          <div key={file.relative_path} className="flex items-center justify-between p-2 border rounded">
            <span>{file.relative_path}</span>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">{(file.size_bytes / 1024).toFixed(1)} KB</span>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm">
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => handleDownload(file.relative_path)}>
                    Download
                  </DropdownMenuItem>
                  <DropdownMenuItem 
                    className="text-red-600"
                    onClick={() => setDeleteTarget(file.relative_path)}
                  >
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        ))}
      </div>

      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete file?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{deleteTarget}"? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} disabled={deleting}>
              {deleting ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
```

**Step 3: Test delete flow**

Upload file → click three-dots → Delete → confirm dialog → verify file deleted and list refreshed.

**Step 4: Commit**

```bash
git add frontend/app/src/components/FileBrowser.tsx
git commit -m "feat: implement file delete with confirmation"
```

---

## Verification

Run all tests:
```bash
uv run python -m pytest tests/test_file_channel_service.py -v
```

Test complete flow:
1. Start backend and frontend
2. Create thread and upload files
3. Verify file browser displays files
4. Test download (file downloads)
5. Test delete (confirmation → file deleted → list refreshed)

