# Rebase `orange/pr105-plus-workspace` onto `origin/main`

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebase the workspace/file-channel feature branch cleanly onto the massively-updated `origin/main`, resolving 9 conflict files without losing any feature work from either side.

**Architecture:** The PR adds workspace-aware file channels (backend service + router endpoints + frontend upload/download UI + mount capability gate). Main has since shipped a 80+ commit overhaul: SSE convergence (P1-P5), background tasks/cron system, unified queue manager, centralized SQLite connection factory, and a full ChatPage refactor. The rebase strategy is a standard `git rebase origin/main` with manual conflict resolution per file, taking care to layer our additions onto main's new structure without reverting its changes.

**Tech Stack:** Python/FastAPI backend, React/TypeScript frontend, SQLite

---

## Pre-flight: understand the conflict map

Files modified by **both** branches (the 9 that will conflict):

| File | Our changes | Main's changes |
|------|-------------|----------------|
| `storage/providers/sqlite/thread_config_repo.py` | Add `workspace_id` column + migration | Switch to `create_connection` factory |
| `backend/web/utils/helpers.py` | Add `workspace_id` to allowed set + load | Switch to `connect_sqlite`, new imports |
| `backend/web/routers/threads.py` | Mount capability gate + file_channel hooks | SSE refactor, queue_manager.enqueue, unregister_wake |
| `frontend/app/src/api/types.ts` | Workspace types, `SandboxType.capability` | Full StreamEventType restructure + ContentEventData |
| `frontend/app/src/pages/ChatPage.tsx` | handleDropUploadFiles + prop | Full refactor: removed useActivities, added useBackgroundTasks |
| `frontend/app/src/components/computer-panel/index.tsx` | File explorer additions | Tab cleanup, AgentsView refactor |
| `frontend/app/src/components/computer-panel/types.ts` | File-explorer props | Minor tab type cleanup |
| `frontend/app/src/components/SandboxSection.tsx` | Capability display | Minor UI polish |
| `frontend/app/package-lock.json` | Lock file for new deps | Lock file for new deps |

Files added by **our branch only** (no conflict, git applies cleanly):
- `backend/web/routers/workspace.py` (extended with channel endpoints — main left it alone after divergence)
- `backend/web/routers/workspaces.py` (new)
- `backend/web/services/file_channel_service.py` (new)
- `backend/web/services/sandbox_service.py` (minor adds)
- `sandbox/` provider files
- `tests/test_file_channel_service.py`, `tests/test_mount_pluggable.py`

---

## Task 1: Backup and start rebase

**Files:** none (git operations only)

**Step 1: Verify the current state is clean**

```bash
git status
git log --oneline -5
```
Expected: working tree clean, HEAD at `27f3b55` or similar.

**Step 2: Start the rebase**

```bash
git rebase origin/main
```

Git will begin replaying our commits. It will pause at the first conflict. The merge commit `459cdf0` will be skipped automatically (it's a `merge` type, not a feature commit).

**Step 3: Note which commit triggered the conflict**

```bash
git status
```

Read the "currently replaying" line. Most conflicts will hit in the early commits (46a3165, 1f1613f, 27f3b55). Resolve and continue as instructed in subsequent tasks.

---

## Task 2: Resolve `storage/providers/sqlite/thread_config_repo.py`

**Strategy:** Main replaced `sqlite3.connect(str(db_path))` with `create_connection(db_path)`. We add `workspace_id` column. Both changes are additive — apply both.

**The resolved file should:**
1. Import `from storage.providers.sqlite.connection import create_connection` (from main)
2. Use `self._conn = create_connection(db_path)` instead of `sqlite3.connect(str(db_path))` (from main)
3. Include `workspace_id` in `update_fields` allowed set (ours)
4. Include `workspace_id` in `lookup_config` SELECT and return dict (ours)
5. Include `workspace_id TEXT` in CREATE TABLE (ours)
6. Include `ALTER TABLE ADD COLUMN workspace_id TEXT` in migration block (ours)

**Step 1: After hitting the conflict, open the file**

```bash
# Read the conflict markers
```

Use the Read tool to see the full conflict state, then Edit to produce the merged result.

**Step 2: Apply the resolution**

The `__init__` method should look like:
```python
def __init__(self, db_path: str | Path, conn: sqlite3.Connection | None = None) -> None:
    self._own_conn = conn is None
    if conn is not None:
        self._conn = conn
    else:
        self._conn = create_connection(db_path)  # ← main's factory
    self._ensure_table()
```

`update_fields` allowed set:
```python
allowed = {"sandbox_type", "cwd", "model", "queue_mode", "observation_provider", "agent", "workspace_id"}
```

`lookup_config` SELECT:
```sql
SELECT sandbox_type, cwd, model, queue_mode, observation_provider, agent, workspace_id
FROM thread_config WHERE thread_id = ?
```

Return dict (index 6 added):
```python
return {
    "sandbox_type": row[0],
    "cwd": row[1],
    "model": row[2],
    "queue_mode": row[3],
    "observation_provider": row[4],
    "agent": row[5],
    "workspace_id": row[6],   # ← ours
}
```

CREATE TABLE adds `workspace_id TEXT` column and migration adds:
```python
if "workspace_id" not in existing_cols:
    self._conn.execute("ALTER TABLE thread_config ADD COLUMN workspace_id TEXT")
```

**Step 3: Stage and continue**

```bash
git add storage/providers/sqlite/thread_config_repo.py
git rebase --continue
```

---

## Task 3: Resolve `backend/web/utils/helpers.py`

**Strategy:** Main migrated `sqlite3.connect` calls to `connect_sqlite`. We added `workspace_id` to `save_thread_config` and `load_thread_config`. Both changes are additive.

**The resolved file should:**
1. Import `from storage.providers.sqlite.kernel import connect_sqlite` (from main)
2. Use `connect_sqlite(path, ...)` in `get_terminal_timestamps`, `get_lease_timestamps`, `delete_thread_in_db` (from main)
3. Have `workspace_id` in `allowed` set in `save_thread_config` (ours)
4. Return `workspace_id=row.get("workspace_id")` in `load_thread_config` (ours)

**Step 1: Read the conflicted file, apply the merged result**

`save_thread_config` allowed set:
```python
allowed = {"sandbox_type", "cwd", "model", "queue_mode", "observation_provider", "agent", "workspace_id"}
```

`load_thread_config` return:
```python
return ThreadConfig(
    sandbox_type=row["sandbox_type"],
    cwd=row["cwd"],
    model=row["model"],
    queue_mode=row["queue_mode"] or "steer",
    observation_provider=row["observation_provider"],
    agent=row.get("agent"),
    workspace_id=row.get("workspace_id"),   # ← ours
)
```

**Step 2: Stage and continue**

```bash
git add backend/web/utils/helpers.py
git rebase --continue
```

---

## Task 4: Resolve `backend/web/routers/threads.py`

**Strategy:** This is the most complex conflict. Main restructured the SSE/streaming/queue APIs; we added mount capability gate functions and file_channel lifecycle hooks. The key is to keep our functions and integrate the file_channel calls with main's `delete_thread` body.

**What main changed in this file:**
- `list_threads`: uses `app.state.thread_tasks` instead of `thread_event_buffers`
- `delete_thread`: adds `app.state.queue_manager.unregister_wake(thread_id)` and uses `thread_event_buffers.pop` instead of `activity_buffers.pop`
- `send_message`: `qm.enqueue(...)` instead of `qm.inject(...)` with `notification_type="steer"`; `start_agent_run` returns `run_id` (not buffer)
- Imports: adds `get_or_create_thread_buffer`, `observe_thread_events`, `ThreadEventBuffer`

**What we added:**
- Imports: `JSONResponse`, `cleanup_thread_file_channel`, `ensure_thread_file_channel`, `init_providers_and_managers`, `MountSpec`
- Functions: `_find_mount_capability_mismatch`, `_validate_mount_capability_gate`
- In `create_thread`: call `ensure_thread_file_channel`
- In `delete_thread`: call `cleanup_thread_file_channel`

**Step 1: Read the full conflicted file**

**Step 2: Apply the resolution**

Imports block — keep ALL of both:
```python
from fastapi.responses import JSONResponse          # ← ours
from backend.web.services.event_buffer import ThreadEventBuffer  # ← main
from backend.web.services.file_channel_service import cleanup_thread_file_channel, ensure_thread_file_channel  # ← ours
from backend.web.services.sandbox_service import destroy_thread_resources_sync, init_providers_and_managers  # ← ours
from backend.web.services.streaming_service import (
    get_or_create_thread_buffer,   # ← main
    observe_run_events,
    observe_thread_events,         # ← main
    start_agent_run,
    start_task_agent_run,
)
from sandbox.config import MountSpec               # ← ours
```

Keep our two helper functions (`_find_mount_capability_mismatch`, `_validate_mount_capability_gate`) before `_get_agent_for_thread` — they have no conflict with main.

In `list_threads`, use main's version:
```python
tasks = app.state.thread_tasks
for t in threads:
    t["sandbox"] = resolve_thread_sandbox(app, t["thread_id"])
    t["running"] = t["thread_id"] in tasks
```

In `delete_thread`, merge both cleanup calls. The final cleanup block should be:
```python
if agent and hasattr(agent, "runtime") and agent.runtime:
    agent.runtime.unbind_thread()
app.state.queue_manager.unregister_wake(thread_id)   # ← main
try:
    await asyncio.to_thread(destroy_thread_resources_sync, thread_id, sandbox_type, app.state.agent_pool)
except Exception as exc:
    ...
await asyncio.to_thread(cleanup_thread_file_channel, thread_id)  # ← ours

app.state.thread_sandbox.pop(thread_id, None)
app.state.thread_cwd.pop(thread_id, None)
app.state.thread_event_buffers.pop(thread_id, None)  # ← main (renamed from activity_buffers)
app.state.queue_manager.clear_all(thread_id)
```

In `send_message`, use main's `enqueue` + `run_id` return:
```python
qm.enqueue(format_steer_reminder(payload.message), thread_id, notification_type="steer")
...
run_id = start_agent_run(agent, thread_id, payload.message, app)
return {"status": "started", "routing": "direct", "run_id": run_id, "thread_id": thread_id}
```

**Step 3: Stage and continue**

```bash
git add backend/web/routers/threads.py
git rebase --continue
```

---

## Task 5: Resolve `frontend/app/src/api/types.ts`

**Strategy:** Main completely restructured `STREAM_EVENT_TYPES` and removed many subagent-specific types. We added workspace types and `SandboxType.capability`. Keep main's type restructure completely; append our workspace types.

**Step 1: Accept main's version of the top of the file**

Main's `STREAM_EVENT_TYPES` (keep exactly):
```typescript
export const STREAM_EVENT_TYPES = [
  "text", "tool_call", "tool_result", "error", "cancelled",
  "task_start", "task_done", "task_error",
  "status", "run_start", "run_done",
] as const;
```

Main's `ContentEventData`, simplified `TaskStartData`/`TaskDoneData`/`TaskErrorData` — keep as-is.

**Step 2: In `SandboxType`, keep our `capability` field addition**

```typescript
export interface SandboxType {
  name: string;
  provider?: string;
  available: boolean;
  reason?: string;
  capability?: {
    can_pause: boolean;
    can_resume: boolean;
    can_destroy: boolean;
    supports_webhook: boolean;
    supports_status_probe: boolean;
    eager_instance_binding: boolean;
    inspect_visible: boolean;
    runtime_kind: string;
    mount: {
      supports_mount: boolean;
      supports_copy: boolean;
      supports_read_only: boolean;
    };
  };
}
```

**Step 3: Append all our workspace types after the existing content**

The workspace types block (everything from `export interface Workspace` through `WorkspaceTransferEntry` and beyond) — keep as-is from our branch.

**Step 4: Remove `agent?: string | null` from `ThreadSummary`**

Main removed this field from `ThreadSummary`. Our branch also removed it in `ThreadSummary`. Accept main's version.

**Step 5: Stage and continue**

```bash
git add frontend/app/src/api/types.ts
git rebase --continue
```

---

## Task 6: Resolve `frontend/app/src/pages/ChatPage.tsx`

**Strategy:** Main rewrote ChatPage significantly. We added file upload handler. Take main's version as the base and inject only our additions.

**What we need to add to main's ChatPage:**
1. Import `type { DroppedUploadFile }` from `../components/InputBox`
2. Import `{ uploadWorkspaceFile }` from `../api`
3. The `handleDropUploadFiles` function body
4. `onDropUploadFiles={handleDropUploadFiles}` prop on `<InputBox>`

**Step 1: Read main's ChatPage (it's 218 lines)**

**Step 2: Add imports at top**

After the existing InputBox import line, add:
```typescript
import InputBox, { type DroppedUploadFile } from "../components/InputBox";
// (replace the plain `import InputBox` line)
```

And add `uploadWorkspaceFile` to the api import block.

**Step 3: Add `handleDropUploadFiles` function**

Place it just before the `return (` statement:
```typescript
async function handleDropUploadFiles(files: DroppedUploadFile[]): Promise<string[]> {
  const uploadedPaths: string[] = [];
  for (const item of files) {
    const payload = await uploadWorkspaceFile(threadId, {
      file: item.file,
      channel: "upload",
      path: item.relativePath,
    });
    uploadedPaths.push(payload.relative_path);
  }
  return uploadedPaths;
}
```

**Step 4: Add prop to InputBox**

Find the `<InputBox` JSX element, add:
```typescript
onDropUploadFiles={handleDropUploadFiles}
```

**Step 5: Stage and continue**

```bash
git add frontend/app/src/pages/ChatPage.tsx
git rebase --continue
```

---

## Task 7: Resolve `frontend/app/src/components/computer-panel/index.tsx`

**Strategy:** Main already has `FilesView` imported (same file). Our diff was relatively small (41 lines). Check if our additions are already present in main's version; if so, accept main's version. If not, integrate.

**Step 1: Read main's version and our diff**

Main's computer-panel/index.tsx already has:
- `import { FilesView } from "./FilesView"` ✓
- `useFileExplorer` hook ✓
- Files tab refresh logic ✓

**Step 2: Compare carefully**

Run:
```bash
git diff origin/main HEAD -- frontend/app/src/components/computer-panel/index.tsx
```

If our changes are already incorporated in main (likely, since FilesView is there), accept main's version:
```bash
git checkout origin/main -- frontend/app/src/components/computer-panel/index.tsx
git add frontend/app/src/components/computer-panel/index.tsx
```

If there are genuinely unique additions on our side (e.g., channel info display, different fileExplorer props), manually merge them in.

**Step 3: Continue**

```bash
git rebase --continue
```

---

## Task 8: Resolve `frontend/app/src/components/computer-panel/types.ts`

**Strategy:** Minor conflict. Read both versions and merge additive changes.

**Step 1: Read the conflicted file**

Main likely updated `TabType` union (removed `"steps"` tab per the cleanup commits). We may have added file-explorer-related props to `ComputerPanelProps`.

**Step 2: Merge**

- Keep main's `TabType` (removed "steps")
- Keep any props we added to `ComputerPanelProps` that aren't in main

**Step 3: Stage and continue**

```bash
git add frontend/app/src/components/computer-panel/types.ts
git rebase --continue
```

---

## Task 9: Resolve `frontend/app/src/components/SandboxSection.tsx`

**Strategy:** Minor conflict. We added capability display (mount mode indicators). Main did UI polish.

**Step 1: Read both diffs**

```bash
git diff 96d6c5e..HEAD -- frontend/app/src/components/SandboxSection.tsx
git diff 96d6c5e..origin/main -- frontend/app/src/components/SandboxSection.tsx
```

**Step 2: Merge**

Take main's UI polish as base; keep our capability-related display code (the mount.supports_* rendering).

**Step 3: Stage and continue**

```bash
git add frontend/app/src/components/SandboxSection.tsx
git rebase --continue
```

---

## Task 10: Resolve `frontend/app/package-lock.json`

**Strategy:** The lock file conflict is mechanical. Both branches added packages; the conflict is a JSON structure mismatch.

**Step 1: Regenerate from scratch**

The cleanest resolution is to delete the conflict and regenerate:
```bash
cd frontend/app
rm package-lock.json
npm install
cd ../..
git add frontend/app/package-lock.json
git rebase --continue
```

This ensures the lock file is consistent with the merged `package.json`.

---

## Task 11: Handle remaining commits

After the first conflicting commit is resolved and `git rebase --continue` is run, git replays the next commit. Repeat Tasks 2-10 as needed for each subsequent commit that conflicts.

**Note:** Most conflicts will cluster in the early commits (46a3165, 1f1613f). Later commits in our branch may apply cleanly once the base conflicts are resolved.

**If git rebase aborts or becomes unresolvable:**
```bash
git rebase --abort
```
Then take the "squash + fresh rebase" fallback: squash all our feature commits into one and rebase.

---

## Task 12: Verify backend

**Step 1: Run tests**

```bash
uv run pytest tests/test_file_channel_service.py tests/test_mount_pluggable.py -v
```

Expected: All pass.

**Step 2: Run broader test suite**

```bash
uv run pytest tests/ -x -q --ignore=tests/test_e2e_complete_frontend_flow.py 2>&1 | tail -20
```

Fix any regressions introduced by the conflict resolutions.

---

## Task 13: Verify frontend builds

**Step 1: Build check**

```bash
cd frontend/app && npm run build 2>&1 | tail -20
```

Expected: No TypeScript errors. If there are type errors in the files we touched (types.ts, ChatPage.tsx), fix them.

**Step 2: Type check**

```bash
cd frontend/app && npx tsc --noEmit 2>&1 | head -30
```

---

## Task 14: Final commit

After all conflicts resolved and tests pass:

```bash
git log --oneline origin/main..HEAD
```

Verify our commits are cleanly on top of main with no leftover conflict markers.

```bash
grep -r "<<<<<<" backend/ frontend/app/src/ storage/ sandbox/ --include="*.py" --include="*.ts" --include="*.tsx"
```

Expected: no output.

If everything is clean, the rebase is complete. Push requires user authorization.

---

## Fallback: Squash rebase

If the multi-commit rebase produces too many cascading conflicts:

```bash
git rebase --abort

# Create a squash branch
git checkout -b orange/pr105-squashed origin/main

# Apply our net changes via diff
git diff 96d6c5e..HEAD | git apply --3way

# Resolve any remaining conflicts once, commit
git add -A
git commit -m "feat: workspace-aware file channels + mount capability gate"
```

This applies the net delta (all our feature work) as a single patch onto main, resolving conflicts only once.
