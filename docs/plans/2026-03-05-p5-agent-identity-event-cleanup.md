# P5: Agent Identity + Event Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove `agent_id` from SSE events, add agent instance persistence, simplify event routing to SSE connection + run_id

**Architecture:** Backend removes all `agent_id` injection/routing, adds `agent_instances.json` for internal identity persistence. Frontend removes `"main"` sentinel checks. Drain loop uses `parent_tool_call_id` presence (internal plumbing) instead of `agent_id != "main"`.

**Tech Stack:** Python (FastAPI backend), TypeScript (React frontend), JSON file storage

**Design doc:** `docs/plans/p5-agent-identity-and-event-cleanup.md`

---

### Task 1: Add agent_id attribute to LeonAgent

**Files:**
- Modify: `agent.py` (LeonAgent.__init__, around line 86-150)

**Step 1: Add agent_id parameter to LeonAgent.__init__**

Find the `__init__` method and add `agent_id: str | None = None` parameter:

```python
def __init__(
    self,
    model_name: str | None = None,
    *,
    workspace_root: str | Path | None = None,
    agent: str | None = None,
    agent_id: str | None = None,  # NEW
    queue_manager: Any = None,
    registry: Any = None,
    verbose: bool = True,
) -> None:
```

Add near the top of `__init__`:
```python
self.agent_id = agent_id
```

**Step 2: Verify no tests break**

Run: `cd /Users/apple/worktrees/leon--feat-chat-refactor && uv run python -c "from agent import LeonAgent; print('OK')"`
Expected: OK (import succeeds, no signature errors)

**Step 3: Commit**

```bash
git add agent.py
git commit -m "feat(p5): add agent_id attribute to LeonAgent"
```

---

### Task 2: Create agent_instances.json persistence layer

**Files:**
- Create: `core/identity/agent_registry.py`

**Step 1: Write the agent registry module**

```python
"""Agent instance identity persistence.

Stores agent identity mappings in ~/.leon/agent_instances.json.
Backend-internal only — agent_id does not leak to SSE events.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

INSTANCES_FILE = Path.home() / ".leon" / "agent_instances.json"


def _load() -> dict[str, Any]:
    if INSTANCES_FILE.exists():
        try:
            return json.loads(INSTANCES_FILE.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load agent_instances.json: %s", e)
    return {}


def _save(data: dict[str, Any]) -> None:
    INSTANCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    INSTANCES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def get_or_create_agent_id(
    *,
    member: str,
    thread_id: str,
    sandbox_type: str,
    member_path: str | None = None,
) -> str:
    """Get existing agent_id for this member+thread combo, or create a new one."""
    instances = _load()

    # Search for existing match
    for aid, info in instances.items():
        if info.get("member") == member and info.get("thread_id") == thread_id and info.get("sandbox_type") == sandbox_type:
            return aid

    # Create new
    import time
    agent_id = uuid.uuid4().hex[:8]
    entry: dict[str, Any] = {
        "member": member,
        "thread_id": thread_id,
        "sandbox_type": sandbox_type,
        "created_at": int(time.time()),
    }
    if member_path:
        entry["member_path"] = member_path

    instances[agent_id] = entry
    _save(instances)
    logger.info("Created agent identity %s for member=%s thread=%s", agent_id, member, thread_id)
    return agent_id
```

**Step 2: Create `core/identity/__init__.py`**

```python
"""Agent identity management."""
```

**Step 3: Verify module loads**

Run: `cd /Users/apple/worktrees/leon--feat-chat-refactor && uv run python -c "from core.identity.agent_registry import get_or_create_agent_id; print('OK')"`
Expected: OK

**Step 4: Commit**

```bash
git add core/identity/
git commit -m "feat(p5): add agent instance identity persistence"
```

---

### Task 3: Wire agent_id into AgentPool

**Files:**
- Modify: `backend/web/services/agent_pool.py` (line 40-86)

**Step 1: Import registry and assign agent_id when creating agents**

Add import at top:
```python
from core.identity.agent_registry import get_or_create_agent_id
```

In `get_or_create_agent`, after creating the LeonAgent instance and before storing in pool, add:
```python
member = agent or "leon"
agent_id = get_or_create_agent_id(
    member=member,
    thread_id=thread_id,
    sandbox_type=sandbox_type,
)
leon_agent.agent_id = agent_id
```

**Step 2: Verify pool still works**

Run: `cd /Users/apple/worktrees/leon--feat-chat-refactor && uv run python -c "from backend.web.services.agent_pool import get_or_create_agent; print('OK')"`
Expected: OK (import succeeds)

**Step 3: Commit**

```bash
git add backend/web/services/agent_pool.py
git commit -m "feat(p5): wire agent_id from registry into AgentPool"
```

---

### Task 4: Remove agent_id from backend event emission

**Files:**
- Modify: `backend/web/services/streaming_service.py` (line 360)
- Modify: `core/task/subagent.py` (3 places: ~L280, ~L744, ~L771)
- Modify: `core/command/middleware.py` (2 places: ~L252, ~L328)

**Step 1: Remove `data["agent_id"] = "main"` from streaming_service.py**

At line 360, delete:
```python
data["agent_id"] = "main"
```

**Step 2: Remove `"agent_id": "main"` from core/task/subagent.py**

3 places in emit_activity_event calls (~L280, ~L744, ~L771). In each, remove the `"agent_id": "main"` key from the JSON dict. Keep `"background": True`.

Example — task_start (~L280):
```python
# Before
"background": True,
"agent_id": "main",

# After
"background": True,
```

Same pattern for task_done (~L744) and task_error (~L771).

**Step 3: Remove `"agent_id": "main"` from core/command/middleware.py**

2 places (~L252 and ~L328). Same pattern: remove `"agent_id": "main"` from the JSON dict, keep `"background": True`.

**Step 4: Commit**

```bash
git add backend/web/services/streaming_service.py core/task/subagent.py core/command/middleware.py
git commit -m "refactor(p5): remove agent_id from all SSE event emission"
```

---

### Task 5: Change drain loop routing in streaming_service.py

**Files:**
- Modify: `backend/web/services/streaming_service.py` (line 619-662)

**Step 1: Read the current drain loop code**

Read `streaming_service.py` lines 610-670 to understand exact current logic.

**Step 2: Replace agent_id routing with parent_tool_call_id presence**

Current pattern:
```python
agent_id = sa_data.get("agent_id", "")
is_subagent_content = (
    agent_id and agent_id != "main"
    and event_type in ("text", "tool_call", "tool_result")
)
```

New pattern:
```python
parent_tcid = sa_data.get("parent_tool_call_id")
is_subagent_content = (
    parent_tcid
    and event_type in ("text", "tool_call", "tool_result")
)
```

Update all `agent_id and agent_id != "main"` checks in the drain loop to use `parent_tcid` instead:

- `task_start` with `parent_tcid` → subagent lifecycle
- `task_done/task_error` with `parent_tcid` → subagent completion
- `task_start/task_done/task_error` with `background: true` and no `parent_tcid` → background task notification

**Step 3: Commit**

```bash
git add backend/web/services/streaming_service.py
git commit -m "refactor(p5): drain loop routes by parent_tool_call_id, not agent_id"
```

---

### Task 6: Remove agent_id from emit_subagent_event

**Files:**
- Modify: `core/monitor/runtime.py` (line 198-231)

**Step 1: Read the current emit_subagent_event method**

Read `core/monitor/runtime.py` lines 195-235.

**Step 2: Remove agent_id parameter and injection**

Remove `agent_id: str | None = None` from the method signature. Remove any code that injects `agent_id` into event data. Keep `parent_tool_call_id` and `background` injection.

**Step 3: Update all callers of emit_subagent_event**

Search for `emit_subagent_event` across the codebase. Remove any `agent_id=...` keyword argument from call sites (likely in `core/task/subagent.py` where it passes `agent_id=task_id`).

**Step 4: Commit**

```bash
git add core/monitor/runtime.py core/task/subagent.py
git commit -m "refactor(p5): remove agent_id from emit_subagent_event"
```

---

### Task 7: Frontend — remove agent_id from types and routing

**Files:**
- Modify: `frontend/app/src/api/types.ts` (~line 18-25)
- Modify: `frontend/app/src/hooks/stream-event-handlers.ts` (~line 161-170)
- Modify: `frontend/app/src/hooks/use-background-tasks.ts` (~line 46)

**Step 1: Update ContentEventData type**

In `types.ts`, change `agent_id: string` to `agent_id?: string` (make optional), or remove entirely. Making it optional is safer for the transition.

```typescript
interface ContentEventData {
  // agent_id removed — not part of SSE protocol
  parent_tool_call_id?: string;
  background?: boolean;
  seq: number;
  run_id: string;
  message_id?: string;
}
```

**Step 2: Update stream-event-handlers.ts routing**

Replace agent_id routing (~line 161-170):

```typescript
// Before
if (agentId && agentId !== "main" && event.type in EVENT_HANDLERS) {
    handleSubagentEvent(event, turnId, onUpdate);
    return { messageId };
}

// After — route by parent_tool_call_id presence
const parentToolCallId = data?.parent_tool_call_id;
if (parentToolCallId && event.type in EVENT_HANDLERS) {
    handleSubagentEvent(event, turnId, onUpdate);
    return { messageId };
}
```

Same for task_start/task_done/task_error routing:
```typescript
// Before
if ((event.type === "task_start" || ...) && agentId && agentId !== "main") {

// After
if ((event.type === "task_start" || ...) && parentToolCallId) {
```

Remove all `agentId` variable declarations that read from `data.agent_id`.

**Step 3: Update use-background-tasks.ts filter**

```typescript
// Before
const isBackgroundTask = data?.background === true && data?.agent_id === "main";

// After
const isBackgroundTask = data?.background === true;
```

**Step 4: Verify frontend builds**

Run: `cd /Users/apple/worktrees/leon--feat-chat-refactor/frontend/app && npm run build`
Expected: Build succeeds with no type errors

**Step 5: Commit**

```bash
git add frontend/app/src/api/types.ts frontend/app/src/hooks/stream-event-handlers.ts frontend/app/src/hooks/use-background-tasks.ts
git commit -m "refactor(p5): frontend removes agent_id routing, uses parent_tool_call_id for subagent nesting"
```

---

### Task 8: Verify end-to-end

**Step 1: Start backend**

Run: `cd /Users/apple/worktrees/leon--feat-chat-refactor && uv run python -m backend.web.main`

**Step 2: Start frontend**

Run: `cd /Users/apple/worktrees/leon--feat-chat-refactor/frontend/app && npm run dev`

**Step 3: Verify with Playwright CLI**

Use `/playwright-cli` to:
1. Send a message → SSE events should have no `agent_id` field
2. Trigger a tool call → normal tool_call → tool_result flow
3. Check background task panel still works

**Step 4: Search for leftover "main" references**

Run: `grep -rn '"main"' frontend/app/src/hooks/ backend/web/services/streaming_service.py core/`
Expected: No `agent_id`-related `"main"` references remain

**Step 5: Check agent_instances.json was created**

Run: `cat ~/.leon/agent_instances.json`
Expected: JSON with at least one entry for the leon agent

**Step 6: Commit verification notes or any fixes**

```bash
git commit -m "verify(p5): end-to-end validation complete"
```
