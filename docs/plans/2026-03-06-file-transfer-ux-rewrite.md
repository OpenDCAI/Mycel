# File Transfer UX Rewrite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current file transfer UI (drag-and-drop + channel panel) with a clean, intuitive interface that separates file upload from message composition and provides clear feedback without polluting the chat.

**Architecture:** Remove drag-and-drop from InputBox, remove channel panel from FilesView. Add a dedicated file attachment button to InputBox that opens a modal for file selection. Use toast notifications (sonner) for upload feedback. Add a "Files" tab to the computer panel that shows uploaded files in a clean list with download actions.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, lucide-react icons, sonner (toast library already in codebase)

---

## Phase 1: Remove Broken UX

### Task 1: Remove drag-and-drop from InputBox

**Files:**
- Modify: `frontend/app/src/components/InputBox.tsx`
- Modify: `frontend/app/src/pages/ChatPage.tsx`

**Step 1: Remove drag-and-drop interface from InputBox**

Remove the `DroppedUploadFile` export and `onDropUploadFiles` prop:

```typescript
// DELETE lines 4-7 (DroppedUploadFile interface)
// DELETE line 16 (onDropUploadFiles prop)
// DELETE lines 26, 30-35 (drag state variables)
// DELETE lines 78-183 (all drag-and-drop handler functions)
// DELETE lines 189-193, 246-252 (drag event handlers and hint text)
```

Keep only the core InputBox functionality (textarea, send button, stop button).

**Step 2: Remove drag-and-drop wiring from ChatPage**

```typescript
// In ChatPage.tsx, DELETE lines 150-161 (handleDropUploadFiles function)
// DELETE line 209 (onDropUploadFiles prop)
```

**Step 3: Verify InputBox still works**

Run: `cd frontend/app && npm run dev`
Test: Type a message and send it. Should work normally without drag functionality.

**Step 4: Commit**

```bash
git add frontend/app/src/components/InputBox.tsx frontend/app/src/pages/ChatPage.tsx
git commit -m "refactor: remove drag-and-drop file upload from InputBox"
```

---

### Task 2: Remove channel panel from FilesView

**Files:**
- Modify: `frontend/app/src/components/computer-panel/FilesView.tsx`
- Modify: `frontend/app/src/components/computer-panel/index.tsx`
- Modify: `frontend/app/src/components/computer-panel/use-file-explorer.ts`

**Step 1: Remove channel UI from FilesView**

```typescript
// In FilesView.tsx:
// DELETE lines 2 (Download, RefreshCw, Upload imports)
// DELETE lines 3 (WorkspaceChannelFileEntry, WorkspaceChannelKind imports)
// DELETE lines 14-20 (channel-related props from interface)
// DELETE lines 22-26 (channel-related event handlers from interface)
// DELETE lines 38-52 (channel props from destructuring)
// DELETE lines 54, 56-77 (fileInputRef, formatBytes, formatTime, upload handlers)
// DELETE lines 134-216 (entire channel panel section)
```

Keep only: file tree, drag handle, file preview.

**Step 2: Remove channel props from ComputerPanel**

```typescript
// In index.tsx:
// DELETE lines 94-100 (channel props passed to FilesView)
// DELETE lines 103-106 (channel event handlers)
```

**Step 3: Remove channel state from use-file-explorer**

```typescript
// In use-file-explorer.ts:
// DELETE lines 5-7, 9-10 (channel-related imports)
// DELETE lines 24-32 (channel-related return type fields)
// DELETE lines 48-56 (channel state variables)
// DELETE lines 124-181 (all channel-related functions)
// DELETE lines 185-195 (channel fields from return object)
```

**Step 4: Verify file browser still works**

Run: `cd frontend/app && npm run dev`
Test: Open computer panel → Files tab. Should show file tree and preview without channel panel.

**Step 5: Commit**

```bash
git add frontend/app/src/components/computer-panel/FilesView.tsx \
        frontend/app/src/components/computer-panel/index.tsx \
        frontend/app/src/components/computer-panel/use-file-explorer.ts
git commit -m "refactor: remove channel panel from FilesView"
```

---

## Phase 2: Add Clean File Attachment UI

### Task 3: Add file attachment button to InputBox

**Files:**
- Modify: `frontend/app/src/components/InputBox.tsx`

**Step 1: Add Paperclip icon import and file input ref**

```typescript
// Add to imports at line 1:
import { Send, Square, Paperclip } from "lucide-react";

// Add after line 33 (after sendingRef):
const fileInputRef = useRef<HTMLInputElement>(null);
```

**Step 2: Add file selection handler stub**

```typescript
// Add before handleSend function (around line 54):
function handleFileSelect(event: React.ChangeEvent<HTMLInputElement>) {
  const files = event.target.files;
  if (!files || files.length === 0) return;
  // TODO: Will wire to upload modal in next task
  console.log("Selected files:", Array.from(files).map(f => f.name));
  event.target.value = ""; // Reset input
}
```

**Step 3: Add paperclip button before send button**

```typescript
// In the button container div (line 223), add BEFORE the send/stop button:
<button
  type="button"
  onClick={() => fileInputRef.current?.click()}
  disabled={inputDisabled}
  className="w-8 h-8 rounded-full flex items-center justify-center transition-colors text-[#737373] hover:text-[#171717] hover:bg-[#f5f5f5] disabled:opacity-50"
  title="Attach files"
>
  <Paperclip className="w-4 h-4" />
</button>

<input
  ref={fileInputRef}
  type="file"
  multiple
  className="hidden"
  onChange={handleFileSelect}
/>
```

**Step 4: Test button appears and triggers file picker**

Run: `cd frontend/app && npm run dev`
Test: Click paperclip icon → file picker opens → select files → console logs file names

**Step 5: Commit**

```bash
git add frontend/app/src/components/InputBox.tsx
git commit -m "feat: add file attachment button to InputBox"
```

---

### Task 4: Create file upload modal component

**Files:**
- Create: `frontend/app/src/components/FileUploadModal.tsx`

**Step 1: Create modal component skeleton**

```typescript
import { useState } from "react";
import { X, Upload, Loader2, CheckCircle2, XCircle } from "lucide-react";

interface FileUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (files: File[]) => Promise<void>;
}

interface FileItem {
  file: File;
  status: "pending" | "uploading" | "success" | "error";
  error?: string;
}

export function FileUploadModal({ isOpen, onClose, onUpload }: FileUploadModalProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [uploading, setUploading] = useState(false);

  if (!isOpen) return null;

  function handleFilesSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files;
    if (!selected) return;
    const items: FileItem[] = Array.from(selected).map(file => ({
      file,
      status: "pending",
    }));
    setFiles(prev => [...prev, ...items]);
    event.target.value = "";
  }

  function removeFile(index: number) {
    setFiles(prev => prev.filter((_, i) => i !== index));
  }

  async function handleUpload() {
    if (files.length === 0) return;
    setUploading(true);

    const filesToUpload = files.filter(f => f.status === "pending").map(f => f.file);

    try {
      await onUpload(filesToUpload);
      setFiles(prev => prev.map(f => f.status === "pending" ? { ...f, status: "success" } : f));
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      setFiles(prev => prev.map(f => f.status === "pending" ? { ...f, status: "error", error: msg } : f));
    } finally {
      setUploading(false);
    }
  }

  function handleClose() {
    if (!uploading) {
      setFiles([]);
      onClose();
    }
  }

  const hasPending = files.some(f => f.status === "pending");
  const allSuccess = files.length > 0 && files.every(f => f.status === "success");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 animate-fade-in">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#e5e5e5]">
          <h2 className="text-sm font-medium text-[#171717]">Upload Files</h2>
          <button
            onClick={handleClose}
            disabled={uploading}
            className="w-6 h-6 rounded flex items-center justify-center text-[#737373] hover:text-[#171717] hover:bg-[#f5f5f5] disabled:opacity-50"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* File list */}
        <div className="flex-1 overflow-auto p-4 space-y-2">
          {files.length === 0 && (
            <div className="text-center py-8 text-sm text-[#a3a3a3]">
              No files selected
            </div>
          )}
          {files.map((item, index) => (
            <div key={index} className="flex items-center gap-2 p-2 rounded border border-[#e5e5e5]">
              <div className="flex-1 min-w-0">
                <div className="text-sm text-[#171717] truncate">{item.file.name}</div>
                <div className="text-xs text-[#737373]">
                  {(item.file.size / 1024).toFixed(1)} KB
                </div>
                {item.error && <div className="text-xs text-red-500 mt-1">{item.error}</div>}
              </div>
              {item.status === "pending" && (
                <button
                  onClick={() => removeFile(index)}
                  disabled={uploading}
                  className="w-6 h-6 rounded flex items-center justify-center text-[#737373] hover:text-red-500 hover:bg-red-50 disabled:opacity-50"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
              {item.status === "uploading" && <Loader2 className="w-4 h-4 animate-spin text-blue-500" />}
              {item.status === "success" && <CheckCircle2 className="w-4 h-4 text-green-500" />}
              {item.status === "error" && <XCircle className="w-4 h-4 text-red-500" />}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-[#e5e5e5]">
          <label className="inline-flex items-center gap-2 px-3 py-1.5 text-sm rounded border border-[#d4d4d4] text-[#404040] hover:bg-[#f5f5f5] cursor-pointer">
            <Upload className="w-4 h-4" />
            Add Files
            <input
              type="file"
              multiple
              className="hidden"
              onChange={handleFilesSelected}
            />
          </label>
          <div className="flex items-center gap-2">
            {allSuccess && (
              <button
                onClick={handleClose}
                className="px-3 py-1.5 text-sm rounded bg-[#171717] text-white hover:bg-[#404040]"
              >
                Done
              </button>
            )}
            {!allSuccess && (
              <>
                <button
                  onClick={handleClose}
                  disabled={uploading}
                  className="px-3 py-1.5 text-sm rounded border border-[#d4d4d4] text-[#404040] hover:bg-[#f5f5f5] disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={() => void handleUpload()}
                  disabled={!hasPending || uploading}
                  className="px-3 py-1.5 text-sm rounded bg-[#171717] text-white hover:bg-[#404040] disabled:opacity-50 inline-flex items-center gap-2"
                >
                  {uploading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Upload
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Test modal renders (stub test)**

Create a test page or add to existing page temporarily to verify modal UI.

**Step 3: Commit**

```bash
git add frontend/app/src/components/FileUploadModal.tsx
git commit -m "feat: create file upload modal component"
```

---

### Task 5: Wire upload modal to InputBox

**Files:**
- Modify: `frontend/app/src/components/InputBox.tsx`
- Modify: `frontend/app/src/pages/ChatPage.tsx`

**Step 1: Add modal state and prop to InputBox**

```typescript
// In InputBox.tsx, add to imports:
import { FileUploadModal } from "./FileUploadModal";

// Add to InputBoxProps interface:
onUploadFiles?: (files: File[]) => Promise<void>;

// Add to component props destructuring:
onUploadFiles,

// Add state after line 35:
const [uploadModalOpen, setUploadModalOpen] = useState(false);

// Replace handleFileSelect function:
function handleFileSelect(event: React.ChangeEvent<HTMLInputElement>) {
  const files = event.target.files;
  if (!files || files.length === 0) return;
  setUploadModalOpen(true);
  // Files will be handled by modal
}

// Update paperclip button onClick:
onClick={() => setUploadModalOpen(true)}

// Remove the hidden file input (we'll use modal's file picker)

// Add modal before closing </div> of component:
{onUploadFiles && (
  <FileUploadModal
    isOpen={uploadModalOpen}
    onClose={() => setUploadModalOpen(false)}
    onUpload={onUploadFiles}
  />
)}
```

**Step 2: Add upload handler to ChatPage**

```typescript
// In ChatPage.tsx, add import:
import { toast } from "sonner";

// Add function after handleDropUploadFiles location (around line 150):
async function handleUploadFiles(files: File[]): Promise<void> {
  const toastId = toast.loading(`Uploading ${files.length} file(s)...`);
  try {
    const uploadedPaths: string[] = [];
    for (const file of files) {
      const payload = await uploadWorkspaceFile(threadId, {
        file,
        channel: "upload",
        path: file.name,
      });
      uploadedPaths.push(payload.relative_path);
    }
    toast.success(`Uploaded ${files.length} file(s)`, { id: toastId });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    toast.error(`Upload failed: ${msg}`, { id: toastId });
    throw error; // Re-throw so modal can show error state
  }
}

// Add prop to InputBox (around line 202):
onUploadFiles={handleUploadFiles}
```

**Step 3: Add Toaster to app root**

```typescript
// In frontend/app/src/main.tsx or App.tsx, add:
import { Toaster } from "./components/ui/sonner";

// Add <Toaster /> component at root level (after RouterProvider or similar)
```

**Step 4: Test full upload flow**

Run: `cd frontend/app && npm run dev`
Test:
1. Click paperclip → modal opens
2. Add files → files appear in list
3. Click Upload → toast shows "Uploading..."
4. Success → toast shows "Uploaded N file(s)"
5. Modal shows checkmarks
6. Click Done → modal closes

**Step 5: Commit**

```bash
git add frontend/app/src/components/InputBox.tsx \
        frontend/app/src/pages/ChatPage.tsx \
        frontend/app/src/main.tsx
git commit -m "feat: wire file upload modal to InputBox with toast feedback"
```

---

## Phase 3: Add Files Tab to Computer Panel

### Task 6: Create uploaded files list component

**Files:**
- Create: `frontend/app/src/components/computer-panel/UploadedFilesView.tsx`

**Step 1: Create component**

```typescript
import { useState, useEffect } from "react";
import { Download, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { listWorkspaceChannelFiles, getWorkspaceDownloadUrl } from "../../api";
import type { WorkspaceChannelFileEntry } from "../../api";

interface UploadedFilesViewProps {
  threadId: string;
}

export function UploadedFilesView({ threadId }: UploadedFilesViewProps) {
  const [files, setFiles] = useState<WorkspaceChannelFileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadFiles() {
    setLoading(true);
    setError(null);
    try {
      const result = await listWorkspaceChannelFiles(threadId, "upload");
      setFiles(result.entries);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadFiles();
  }, [threadId]);

  function handleDownload(relativePath: string) {
    const url = getWorkspaceDownloadUrl(threadId, relativePath, "upload");
    window.open(url, "_blank", "noopener,noreferrer");
  }

  function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatTime(iso: string): string {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return date.toLocaleString();
  }

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header */}
      <div className="px-3 py-2 border-b border-[#e5e5e5] flex items-center justify-between">
        <div className="text-xs font-medium text-[#171717]">Uploaded Files</div>
        <button
          onClick={() => void loadFiles()}
          disabled={loading}
          className="w-7 h-7 rounded flex items-center justify-center text-[#737373] hover:text-[#171717] hover:bg-[#f5f5f5] disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* File list */}
      <div className="flex-1 overflow-auto">
        {error && (
          <div className="px-3 py-2 text-xs text-red-500">{error}</div>
        )}
        {!error && loading && (
          <div className="flex items-center gap-2 px-3 py-2 text-xs text-[#737373]">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Loading files...
          </div>
        )}
        {!error && !loading && files.length === 0 && (
          <div className="px-3 py-8 text-center text-sm text-[#a3a3a3]">
            No files uploaded yet
          </div>
        )}
        {!error && !loading && files.map((file) => (
          <div
            key={file.relative_path}
            className="px-3 py-2 border-b border-[#f5f5f5] hover:bg-[#fafafa] flex items-center gap-2"
          >
            <div className="flex-1 min-w-0">
              <div className="text-sm text-[#171717] truncate" title={file.relative_path}>
                {file.relative_path}
              </div>
              <div className="text-xs text-[#737373]">
                {formatBytes(file.size_bytes)} · {formatTime(file.updated_at)}
              </div>
            </div>
            <button
              onClick={() => handleDownload(file.relative_path)}
              className="w-7 h-7 rounded flex items-center justify-center text-[#737373] hover:text-[#171717] hover:bg-[#f5f5f5]"
              title="Download"
            >
              <Download className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/src/components/computer-panel/UploadedFilesView.tsx
git commit -m "feat: create uploaded files list component"
```

---

### Task 7: Add "Uploads" tab to computer panel

**Files:**
- Modify: `frontend/app/src/components/computer-panel/types.ts`
- Modify: `frontend/app/src/components/computer-panel/TabBar.tsx`
- Modify: `frontend/app/src/components/computer-panel/index.tsx`

**Step 1: Add "uploads" tab type**

```typescript
// In types.ts, modify TabType:
export type TabType = "terminal" | "files" | "uploads" | "agents";
```

**Step 2: Add tab to TabBar**

```typescript
// In TabBar.tsx, add to TABS array:
import { Upload } from "lucide-react";

const TABS: { key: TabType; label: string; icon: typeof Terminal }[] = [
  { key: "terminal", label: "Terminal", icon: Terminal },
  { key: "files", label: "Files", icon: FileText },
  { key: "uploads", label: "Uploads", icon: Upload },
  { key: "agents", label: "Agents", icon: Bot },
];
```

**Step 3: Add uploads view to ComputerPanel**

```typescript
// In index.tsx, add import:
import { UploadedFilesView } from "./UploadedFilesView";

// Add view in render section (after files view):
{activeTab === "uploads" && (
  <UploadedFilesView threadId={threadId} />
)}
```

**Step 4: Test uploads tab**

Run: `cd frontend/app && npm run dev`
Test:
1. Upload files via paperclip button
2. Open computer panel
3. Click "Uploads" tab
4. Should see uploaded files
5. Click download → file downloads

**Step 5: Commit**

```bash
git add frontend/app/src/components/computer-panel/types.ts \
        frontend/app/src/components/computer-panel/TabBar.tsx \
        frontend/app/src/components/computer-panel/index.tsx
git commit -m "feat: add Uploads tab to computer panel"
```

---

## Phase 4: Polish and Cleanup

### Task 8: Remove unused API client methods

**Files:**
- Modify: `frontend/app/src/api/client.ts`
- Modify: `frontend/app/src/api/types.ts`

**Step 1: Remove channel-related exports that are no longer used**

```typescript
// In client.ts, keep only:
// - uploadWorkspaceFile (used by ChatPage)
// - listWorkspaceChannelFiles (used by UploadedFilesView)
// - getWorkspaceDownloadUrl (used by UploadedFilesView)

// Remove if unused:
// - getWorkspaceChannels
// - listWorkspaceTransfers
```

**Step 2: Clean up types**

```typescript
// In types.ts, keep only types actually used:
// - WorkspaceChannelFileEntry
// - WorkspaceChannelKind
// - WorkspaceUploadResult

// Remove if unused:
// - WorkspaceChannelInfo
// - WorkspaceChannelsResult
// - WorkspaceTransferEntry
```

**Step 3: Verify build**

Run: `cd frontend/app && npm run build`
Expected: No TypeScript errors

**Step 4: Commit**

```bash
git add frontend/app/src/api/client.ts frontend/app/src/api/types.ts
git commit -m "refactor: remove unused channel API methods"
```

---

### Task 9: Update language consistency

**Files:**
- Modify: `frontend/app/src/components/computer-panel/TabBar.tsx`
- Modify: `frontend/app/src/components/computer-panel/UploadedFilesView.tsx`

**Step 1: Standardize to English**

```typescript
// In TabBar.tsx, update labels:
const TABS = [
  { key: "terminal", label: "Terminal", icon: Terminal },
  { key: "files", label: "Files", icon: FileText },
  { key: "uploads", label: "Uploads", icon: Upload },
  { key: "agents", label: "Agents", icon: Bot },
];
```

**Step 2: Commit**

```bash
git add frontend/app/src/components/computer-panel/TabBar.tsx
git commit -m "refactor: standardize UI language to English"
```

---

### Task 10: Add empty state illustration (optional polish)

**Files:**
- Modify: `frontend/app/src/components/computer-panel/UploadedFilesView.tsx`

**Step 1: Enhance empty state**

```typescript
// Replace empty state div with:
<div className="px-3 py-12 text-center">
  <Upload className="w-12 h-12 mx-auto mb-3 text-[#d4d4d4]" />
  <div className="text-sm text-[#a3a3a3] mb-1">No files uploaded yet</div>
  <div className="text-xs text-[#d4d4d4]">
    Use the paperclip button in the chat input to upload files
  </div>
</div>
```

**Step 2: Commit**

```bash
git add frontend/app/src/components/computer-panel/UploadedFilesView.tsx
git commit -m "polish: enhance empty state in uploads view"
```

---

## Testing Checklist

After all tasks complete, verify:

- [ ] Paperclip button appears in InputBox
- [ ] Clicking paperclip opens file upload modal
- [ ] Can select multiple files in modal
- [ ] Can remove files before upload
- [ ] Upload shows loading toast
- [ ] Success shows success toast
- [ ] Uploaded files appear in Uploads tab
- [ ] Can download files from Uploads tab
- [ ] Refresh button works in Uploads tab
- [ ] No drag-and-drop hint text appears
- [ ] No channel panel appears in Files tab
- [ ] Files tab still shows workspace file tree
- [ ] All UI text is in English
- [ ] No console errors
- [ ] Build passes: `npm run build`

---

## Rollout

1. Test on local sandbox thread
2. Test on remote sandbox thread (daytona/docker)
3. Verify workspace-backed threads work correctly
4. Create PR with before/after screenshots
5. Document new UX in user-facing docs (if any)

