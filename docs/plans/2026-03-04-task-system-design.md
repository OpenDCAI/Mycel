# Task System V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Cron task production + Agent task consumption + Dashboard enhancement to Leon's existing panel_tasks system.

**Architecture:** Lightweight in-process approach. APScheduler runs inside FastAPI for Cron. New TaskBoardMiddleware gives agents tools to claim/execute board tasks. Existing TasksPage enhanced with Cron tab and real-time updates.

**Tech Stack:** APScheduler 4.x, SQLite, FastAPI, LangChain middleware, React + Zustand + shadcn/ui

---

## Phase 1: Data Layer

### Task 1: Extend panel_tasks schema

**Files:**
- Modify: `backend/web/services/task_service.py:10-24` (schema + helpers)
- Test: `tests/test_task_service.py` (new)

**Step 1: Write failing test for new columns**

```python
# tests/test_task_service.py
import os
import tempfile
import pytest

@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch, tmp_path):
    db = tmp_path / "test.db"
    monkeypatch.setattr("backend.web.services.task_service.DB_PATH", str(db))

def test_create_task_has_new_fields():
    from backend.web.services.task_service import create_task, list_tasks
    task = create_task(title="Test", source="cron", cron_job_id="cron-1")
    assert task["source"] == "cron"
    assert task["cron_job_id"] == "cron-1"
    assert task["thread_id"] == ""
    assert task["result"] == ""
    assert task["started_at"] == 0
    assert task["completed_at"] == 0

def test_update_task_new_fields():
    from backend.web.services.task_service import create_task, update_task
    task = create_task(title="Test")
    updated = update_task(task["id"], thread_id="thread-abc", progress=50, started_at=1000)
    assert updated["thread_id"] == "thread-abc"
    assert updated["started_at"] == 1000
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/apple/worktrees/leon--feat-task-system
uv run pytest tests/test_task_service.py -v
```

Expected: FAIL — `create_task()` doesn't accept `source` param, columns don't exist.

**Step 3: Update schema and functions in task_service.py**

In `_ensure_tasks_table`, add 6 new columns to CREATE TABLE:

```python
def _ensure_tasks_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS panel_tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            assignee_id TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            priority TEXT DEFAULT 'medium',
            progress INTEGER DEFAULT 0,
            deadline TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            thread_id TEXT DEFAULT '',
            source TEXT DEFAULT 'manual',
            cron_job_id TEXT DEFAULT '',
            result TEXT DEFAULT '',
            started_at INTEGER DEFAULT 0,
            completed_at INTEGER DEFAULT 0
        )
    """)
    # Migration: add columns to existing tables
    for col, default in [
        ("thread_id", "''"), ("source", "'manual'"), ("cron_job_id", "''"),
        ("result", "''"), ("started_at", "0"), ("completed_at", "0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE panel_tasks ADD COLUMN {col} TEXT DEFAULT {default}")
        except sqlite3.OperationalError:
            pass  # column already exists
```

Update `create_task` ALLOWED_FIELDS to include new columns:

```python
def create_task(**fields: Any) -> dict[str, Any]:
    conn = _tasks_conn()
    task_id = str(int(time.time() * 1000))
    allowed = {
        "title", "description", "assignee_id", "status", "priority",
        "progress", "deadline", "thread_id", "source", "cron_job_id",
        "result", "started_at", "completed_at",
    }
    data = {k: v for k, v in fields.items() if k in allowed}
    # ... rest of insert logic
```

Update `update_task` ALLOWED_FIELDS similarly.

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_task_service.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/web/services/task_service.py tests/test_task_service.py
git commit -m "feat(task): extend panel_tasks schema with thread/source/cron/result fields"
```

---

### Task 2: Create cron_jobs service

**Files:**
- Create: `backend/web/services/cron_job_service.py`
- Test: `tests/test_cron_job_service.py` (new)

**Step 1: Write failing test**

```python
# tests/test_cron_job_service.py
import pytest

@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch, tmp_path):
    db = tmp_path / "test.db"
    monkeypatch.setattr("backend.web.services.cron_job_service.DB_PATH", str(db))

def test_crud_lifecycle():
    from backend.web.services.cron_job_service import (
        create_cron_job, list_cron_jobs, update_cron_job, delete_cron_job,
    )
    job = create_cron_job(name="Daily check", cron_expression="0 9 * * *",
                          task_template='{"title":"Daily check","priority":"high"}')
    assert job["name"] == "Daily check"
    assert job["enabled"] == 1

    jobs = list_cron_jobs()
    assert len(jobs) == 1

    updated = update_cron_job(job["id"], enabled=0)
    assert updated["enabled"] == 0

    assert delete_cron_job(job["id"]) is True
    assert len(list_cron_jobs()) == 0

def test_create_requires_name_and_expression():
    from backend.web.services.cron_job_service import create_cron_job
    with pytest.raises(ValueError):
        create_cron_job(name="", cron_expression="0 9 * * *")
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_cron_job_service.py -v
```

Expected: FAIL — module doesn't exist.

**Step 3: Implement cron_job_service.py**

```python
# backend/web/services/cron_job_service.py
"""CRUD operations for cron_jobs table."""
import json
import sqlite3
import time
from typing import Any

from backend.web.core.config import DB_PATH


def _ensure_cron_jobs_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cron_jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            cron_expression TEXT NOT NULL,
            task_template TEXT DEFAULT '{}',
            enabled INTEGER DEFAULT 1,
            last_run_at INTEGER DEFAULT 0,
            next_run_at INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL
        )
    """)


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    _ensure_cron_jobs_table(c)
    return c


def list_cron_jobs() -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute("SELECT * FROM cron_jobs ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cron_job(job_id: str) -> dict[str, Any] | None:
    conn = _conn()
    row = conn.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_cron_job(*, name: str, cron_expression: str, **fields: Any) -> dict[str, Any]:
    if not name.strip():
        raise ValueError("name is required")
    if not cron_expression.strip():
        raise ValueError("cron_expression is required")
    conn = _conn()
    job_id = str(int(time.time() * 1000))
    allowed = {"description", "task_template", "enabled"}
    data = {k: v for k, v in fields.items() if k in allowed}
    cols = ["id", "name", "cron_expression", "created_at"] + list(data.keys())
    vals = [job_id, name, cron_expression, int(time.time() * 1000)] + list(data.values())
    placeholders = ",".join("?" * len(cols))
    conn.execute(f"INSERT INTO cron_jobs ({','.join(cols)}) VALUES ({placeholders})", vals)
    conn.commit()
    row = conn.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row)


def update_cron_job(job_id: str, **fields: Any) -> dict[str, Any] | None:
    allowed = {"name", "description", "cron_expression", "task_template",
               "enabled", "last_run_at", "next_run_at"}
    data = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not data:
        return get_cron_job(job_id)
    conn = _conn()
    sets = ",".join(f"{k}=?" for k in data)
    conn.execute(f"UPDATE cron_jobs SET {sets} WHERE id = ?", [*data.values(), job_id])
    conn.commit()
    row = conn.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_cron_job(job_id: str) -> bool:
    conn = _conn()
    cur = conn.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0
```

**Step 4: Run test**

```bash
uv run pytest tests/test_cron_job_service.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/web/services/cron_job_service.py tests/test_cron_job_service.py
git commit -m "feat(task): add cron_jobs CRUD service with SQLite storage"
```

---

## Phase 2: Cron System

### Task 3: CronService with APScheduler

**Files:**
- Create: `backend/web/services/cron_service.py`
- Test: `tests/test_cron_service.py` (new)

**Step 1: Add APScheduler dependency**

```bash
cd /Users/apple/worktrees/leon--feat-task-system
uv add apscheduler>=4.0
```

**Step 2: Write failing test**

```python
# tests/test_cron_service.py
import asyncio
import pytest

@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch, tmp_path):
    db = tmp_path / "test.db"
    monkeypatch.setattr("backend.web.services.cron_job_service.DB_PATH", str(db))
    monkeypatch.setattr("backend.web.services.task_service.DB_PATH", str(db))

@pytest.mark.asyncio
async def test_cron_trigger_creates_task():
    from backend.web.services.cron_job_service import create_cron_job
    from backend.web.services.cron_service import CronService
    from backend.web.services.task_service import list_tasks
    import json

    job = create_cron_job(
        name="Test job",
        cron_expression="* * * * *",
        task_template=json.dumps({"title": "Auto task", "priority": "high"}),
    )

    service = CronService()
    # Directly test the trigger function
    await service.trigger_job(job["id"])

    tasks = list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Auto task"
    assert tasks[0]["priority"] == "high"
    assert tasks[0]["source"] == "cron"
    assert tasks[0]["cron_job_id"] == job["id"]
```

**Step 3: Run to verify failure**

```bash
uv run pytest tests/test_cron_service.py -v
```

**Step 4: Implement CronService**

```python
# backend/web/services/cron_service.py
"""Cron scheduler service using APScheduler."""
import asyncio
import json
import logging
import time
from typing import Any

from apscheduler.schedulers.async_ import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.web.services import cron_job_service, task_service

logger = logging.getLogger(__name__)


class CronService:
    def __init__(self) -> None:
        self._scheduler: AsyncScheduler | None = None
        self._running = False

    async def start(self) -> None:
        """Load all enabled cron jobs and start the scheduler."""
        self._scheduler = AsyncScheduler()
        await self._scheduler.__aenter__()
        self._running = True

        jobs = await asyncio.to_thread(cron_job_service.list_cron_jobs)
        for job in jobs:
            if job["enabled"]:
                await self._register_job(job)
        logger.info("CronService started with %d jobs", len(jobs))

    async def stop(self) -> None:
        """Gracefully stop the scheduler."""
        if self._scheduler and self._running:
            await self._scheduler.__aexit__(None, None, None)
            self._running = False
            logger.info("CronService stopped")

    async def _register_job(self, job: dict[str, Any]) -> None:
        """Register a single cron job with APScheduler."""
        if not self._scheduler:
            return
        try:
            trigger = CronTrigger.from_crontab(job["cron_expression"])
            await self._scheduler.add_schedule(
                self._on_trigger,
                trigger,
                id=job["id"],
                args=[job["id"]],
            )
        except Exception:
            logger.exception("Failed to register cron job %s", job["id"])

    async def trigger_job(self, job_id: str) -> dict[str, Any] | None:
        """Trigger a cron job immediately (manual or scheduled)."""
        return await self._on_trigger(job_id)

    async def _on_trigger(self, job_id: str) -> dict[str, Any] | None:
        """Called when a cron job fires. Creates a task from the template."""
        job = await asyncio.to_thread(cron_job_service.get_cron_job, job_id)
        if not job or not job["enabled"]:
            return None

        template = json.loads(job["task_template"]) if job["task_template"] else {}
        template.setdefault("title", job["name"])
        template["source"] = "cron"
        template["cron_job_id"] = job_id

        task = await asyncio.to_thread(task_service.create_task, **template)

        now = int(time.time() * 1000)
        await asyncio.to_thread(cron_job_service.update_cron_job, job_id, last_run_at=now)

        logger.info("Cron job %s triggered, created task %s", job_id, task["id"])
        return task

    async def add_job(self, job: dict[str, Any]) -> None:
        """Add a new job to the running scheduler."""
        if job["enabled"]:
            await self._register_job(job)

    async def remove_job(self, job_id: str) -> None:
        """Remove a job from the running scheduler."""
        if self._scheduler:
            try:
                await self._scheduler.remove_schedule(job_id)
            except Exception:
                pass  # job may not be registered

    async def update_job(self, job: dict[str, Any]) -> None:
        """Update a job: remove old schedule, re-register if enabled."""
        await self.remove_job(job["id"])
        if job["enabled"]:
            await self._register_job(job)
```

**Step 5: Run test**

```bash
uv run pytest tests/test_cron_service.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add backend/web/services/cron_service.py tests/test_cron_service.py pyproject.toml uv.lock
git commit -m "feat(task): add CronService with APScheduler for scheduled task creation"
```

---

### Task 4: Cron REST API endpoints

**Files:**
- Modify: `backend/web/routers/panel.py:81+` (add cron endpoints)
- Modify: `backend/web/models/panel.py:53+` (add cron request models)
- Test: `tests/test_cron_api.py` (new)

**Step 1: Add Pydantic models**

Add to `backend/web/models/panel.py`:

```python
class CreateCronJobRequest(BaseModel):
    name: str
    description: str = ""
    cron_expression: str
    task_template: str = "{}"  # JSON string
    enabled: bool = True

class UpdateCronJobRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    cron_expression: str | None = None
    task_template: str | None = None
    enabled: bool | None = None
```

**Step 2: Add endpoints to panel.py**

```python
# In backend/web/routers/panel.py, after task endpoints

# --- Cron Jobs ---

@router.get("/cron-jobs")
async def list_cron_jobs():
    items = await asyncio.to_thread(cron_job_service.list_cron_jobs)
    return {"items": items}

@router.post("/cron-jobs")
async def create_cron_job(req: CreateCronJobRequest):
    job = await asyncio.to_thread(
        cron_job_service.create_cron_job,
        name=req.name, cron_expression=req.cron_expression,
        description=req.description, task_template=req.task_template,
        enabled=int(req.enabled),
    )
    # Register with running scheduler if available
    app = router.app  # access via request if needed
    return {"item": job}

@router.put("/cron-jobs/{job_id}")
async def update_cron_job(job_id: str, req: UpdateCronJobRequest):
    fields = req.model_dump(exclude_none=True)
    if "enabled" in fields:
        fields["enabled"] = int(fields["enabled"])
    job = await asyncio.to_thread(cron_job_service.update_cron_job, job_id, **fields)
    if not job:
        raise HTTPException(404, "Cron job not found")
    return {"item": job}

@router.delete("/cron-jobs/{job_id}")
async def delete_cron_job(job_id: str):
    ok = await asyncio.to_thread(cron_job_service.delete_cron_job, job_id)
    if not ok:
        raise HTTPException(404, "Cron job not found")
    return {"ok": True}

@router.post("/cron-jobs/{job_id}/run")
async def trigger_cron_job(job_id: str, request: Request):
    cron_service: CronService | None = getattr(request.app.state, "cron_service", None)
    if not cron_service:
        raise HTTPException(503, "Cron service not available")
    task = await cron_service.trigger_job(job_id)
    if not task:
        raise HTTPException(404, "Cron job not found or disabled")
    return {"item": task}
```

**Step 3: Write API test**

```python
# tests/test_cron_api.py
"""Test cron job API endpoints via FastAPI test client."""
import pytest
from unittest.mock import patch

# Integration test that verifies routes are wired correctly
# Full e2e test requires running server — keep unit-level here

def test_cron_job_models():
    from backend.web.models.panel import CreateCronJobRequest, UpdateCronJobRequest
    req = CreateCronJobRequest(name="Test", cron_expression="0 9 * * *")
    assert req.enabled is True
    assert req.task_template == "{}"

    update = UpdateCronJobRequest(enabled=False)
    assert update.name is None
    assert update.enabled is False
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_cron_api.py tests/test_cron_job_service.py -v
```

**Step 5: Commit**

```bash
git add backend/web/routers/panel.py backend/web/models/panel.py tests/test_cron_api.py
git commit -m "feat(task): add cron job REST API endpoints"
```

---

### Task 5: Wire CronService into FastAPI lifespan

**Files:**
- Modify: `backend/web/core/lifespan.py:15-65`

**Step 1: Add CronService to lifespan startup/shutdown**

Follow `idle_reaper_task` pattern:

```python
# In lifespan(), before the try block:
app.state.cron_service: CronService | None = None

# Inside try block, after idle_reaper_task:
from backend.web.services.cron_service import CronService
cron_svc = CronService()
await cron_svc.start()
app.state.cron_service = cron_svc

# In finally block:
if app.state.cron_service:
    await app.state.cron_service.stop()
```

**Step 2: Verify by starting the backend**

```bash
cd /Users/apple/worktrees/leon--feat-task-system
uv run python -m backend.web.main
```

Check logs for "CronService started". Ctrl+C and check "CronService stopped".

**Step 3: Commit**

```bash
git add backend/web/core/lifespan.py
git commit -m "feat(task): wire CronService into FastAPI lifespan"
```

---

## Phase 3: Agent Consumption

### Task 6: TaskBoardMiddleware with agent tools

**Files:**
- Create: `core/taskboard/__init__.py`
- Create: `core/taskboard/middleware.py`
- Test: `tests/test_taskboard_middleware.py` (new)

**Step 1: Write failing test**

```python
# tests/test_taskboard_middleware.py
import json
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import ToolMessage

@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch, tmp_path):
    db = tmp_path / "test.db"
    monkeypatch.setattr("backend.web.services.task_service.DB_PATH", str(db))
    monkeypatch.setattr("backend.web.services.cron_job_service.DB_PATH", str(db))

def test_tool_schemas_registered():
    from core.taskboard.middleware import TaskBoardMiddleware
    mw = TaskBoardMiddleware()
    schemas = mw._get_tool_schemas()
    names = {s["function"]["name"] for s in schemas}
    assert "ListBoardTasks" in names
    assert "ClaimTask" in names
    assert "CompleteTask" in names
    assert "CreateBoardTask" in names

def test_create_board_task():
    from core.taskboard.middleware import TaskBoardMiddleware
    from backend.web.services.task_service import list_tasks
    mw = TaskBoardMiddleware()
    result = mw._handle_tool_call(MagicMock(
        name="CreateBoardTask",
        args={"Title": "Test task", "Description": "Do something", "Priority": "high"},
        id="call-1",
    ))
    assert isinstance(result, ToolMessage)
    data = json.loads(result.content)
    assert data["title"] == "Test task"
    tasks = list_tasks()
    assert len(tasks) == 1

def test_claim_and_complete():
    from core.taskboard.middleware import TaskBoardMiddleware
    from backend.web.services.task_service import create_task, list_tasks
    mw = TaskBoardMiddleware()
    mw.thread_id = "thread-123"

    task = create_task(title="Pending task")
    # Claim
    result = mw._handle_tool_call(MagicMock(
        name="ClaimTask", args={"TaskId": task["id"]}, id="call-2"))
    data = json.loads(result.content)
    assert data["status"] == "running"

    # Complete
    result = mw._handle_tool_call(MagicMock(
        name="CompleteTask",
        args={"TaskId": task["id"], "Result": "Done successfully"},
        id="call-3",
    ))
    data = json.loads(result.content)
    assert data["status"] == "completed"
    assert data["result"] == "Done successfully"
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_taskboard_middleware.py -v
```

**Step 3: Implement TaskBoardMiddleware**

Create `core/taskboard/__init__.py` (empty) and `core/taskboard/middleware.py`:

Follow the `TodoMiddleware` pattern exactly — `wrap_model_call` injects tool schemas, `wrap_tool_call` intercepts by name.

Tools:
- `ListBoardTasks(Status?, Priority?)` → calls `task_service.list_tasks()` with filtering
- `ClaimTask(TaskId)` → `update_task(id, status="running", thread_id=self.thread_id, started_at=now)`
- `UpdateTaskProgress(TaskId, Progress, Note?)` → `update_task(id, progress=N)`
- `CompleteTask(TaskId, Result)` → `update_task(id, status="completed", result=R, progress=100, completed_at=now)`
- `FailTask(TaskId, Reason)` → `update_task(id, status="failed", result=R, completed_at=now)`
- `CreateBoardTask(Title, Description, Priority?, CronExpression?)` → `create_task(...)`, optionally `create_cron_job(...)`

Key: `self.thread_id` must be set externally when the middleware is attached to an agent running in a specific thread.

**Step 4: Run tests**

```bash
uv run pytest tests/test_taskboard_middleware.py -v
```

**Step 5: Commit**

```bash
git add core/taskboard/ tests/test_taskboard_middleware.py
git commit -m "feat(task): add TaskBoardMiddleware with agent tools for board task management"
```

---

### Task 7: Register middleware in agent.py

**Files:**
- Modify: `agent.py:768-780` (add TaskBoardMiddleware after TodoMiddleware)

**Step 1: Add TaskBoardMiddleware to middleware stack**

In `_build_middleware_stack()`, after TodoMiddleware (line 768-769):

```python
# 9. Todo
self._todo_middleware = TodoMiddleware(verbose=self.verbose)
middleware.append(self._todo_middleware)

# 10. TaskBoard (agent ↔ panel_tasks)
from core.taskboard.middleware import TaskBoardMiddleware
self._taskboard_middleware = TaskBoardMiddleware()
middleware.append(self._taskboard_middleware)

# 11. Task (sub-agent orchestration)
# ... existing TaskMiddleware code
```

**Step 2: Set thread_id on the middleware when agent is used in a thread**

In the backend's `streaming_service.py` or `agent_pool.py`, after getting/creating an agent for a thread, set:

```python
if hasattr(agent, '_taskboard_middleware'):
    agent._taskboard_middleware.thread_id = thread_id
```

**Step 3: Verify by starting backend and checking agent tools**

Start backend, create a thread, send a message. Agent should now have `ListBoardTasks`, `ClaimTask`, etc. in its available tools.

**Step 4: Commit**

```bash
git add agent.py backend/web/services/streaming_service.py
git commit -m "feat(task): register TaskBoardMiddleware in agent middleware stack"
```

---

### Task 8: Idle auto-pickup callback

**Files:**
- Modify: `core/taskboard/middleware.py` (add `on_idle` method)
- Modify: `backend/web/services/streaming_service.py` (register callback on state change)

**Step 1: Add on_idle to TaskBoardMiddleware**

```python
# In TaskBoardMiddleware
async def on_idle(self) -> dict[str, Any] | None:
    """Called when agent enters IDLE state. Check for pending tasks."""
    if not self.auto_claim:
        return None
    tasks = await asyncio.to_thread(task_service.list_tasks)
    pending = [t for t in tasks if t["status"] == "pending"]
    if not pending:
        return None
    # Sort: high > medium > low, then oldest first
    priority_order = {"high": 0, "medium": 1, "low": 2}
    pending.sort(key=lambda t: (priority_order.get(t["priority"], 9), t["created_at"]))
    return pending[0]  # Return the task to claim, let caller decide
```

**Step 2: In streaming_service.py, after agent enters IDLE state, check for tasks**

After `agent.runtime.transition(AgentState.IDLE)`:

```python
# Check for pending board tasks
if hasattr(agent, '_taskboard_middleware'):
    next_task = await agent._taskboard_middleware.on_idle()
    if next_task:
        # TODO: Either auto-claim and execute, or notify frontend
        logger.info("Pending board task available: %s", next_task["id"])
```

Full implementation of auto-execution is deferred to after basic tools work end-to-end. The callback infrastructure is the key piece.

**Step 3: Commit**

```bash
git add core/taskboard/middleware.py backend/web/services/streaming_service.py
git commit -m "feat(task): add idle auto-pickup callback for board tasks"
```

---

## Phase 4: Frontend Enhancement

### Task 9: Extend TypeScript types and store

**Files:**
- Modify: `frontend/app/src/store/types.ts:53-66`
- Modify: `frontend/app/src/store/app-store.ts:149-188`

**Step 1: Update Task type**

In `types.ts`, extend Task interface:

```typescript
export type TaskSource = "manual" | "cron" | "agent" | "queue";

export interface Task {
  id: string;
  title: string;
  description: string;
  assignee_id: string;
  status: TaskStatus;
  priority: Priority;
  progress: number;
  deadline: string;
  created_at: number;
  // New fields
  thread_id: string;
  source: TaskSource;
  cron_job_id: string;
  result: string;
  started_at: number;
  completed_at: number;
}

export interface CronJob {
  id: string;
  name: string;
  description: string;
  cron_expression: string;
  task_template: string;
  enabled: number;  // 0 | 1
  last_run_at: number;
  next_run_at: number;
  created_at: number;
}
```

**Step 2: Add cron store methods in app-store.ts**

```typescript
// Add to AppState interface
cronJobs: CronJob[];
fetchCronJobs: () => Promise<void>;
addCronJob: (fields?: Partial<CronJob>) => Promise<CronJob>;
updateCronJob: (id: string, fields: Partial<CronJob>) => Promise<void>;
deleteCronJob: (id: string) => Promise<void>;
triggerCronJob: (id: string) => Promise<void>;

// Add implementations
fetchCronJobs: async () => {
  const data = await api<{ items: CronJob[] }>("GET", "/cron-jobs");
  set({ cronJobs: data.items });
},
addCronJob: async (fields) => {
  const data = await api<{ item: CronJob }>("POST", "/cron-jobs", fields);
  set(s => ({ cronJobs: [data.item, ...s.cronJobs] }));
  return data.item;
},
updateCronJob: async (id, fields) => {
  const data = await api<{ item: CronJob }>("PUT", `/cron-jobs/${id}`, fields);
  set(s => ({ cronJobs: s.cronJobs.map(j => j.id === id ? data.item : j) }));
},
deleteCronJob: async (id) => {
  await api("DELETE", `/cron-jobs/${id}`);
  set(s => ({ cronJobs: s.cronJobs.filter(j => j.id !== id) }));
},
triggerCronJob: async (id) => {
  await api<{ item: any }>("POST", `/cron-jobs/${id}/run`);
},
```

Add `fetchCronJobs` to `loadAll()`.

**Step 3: Commit**

```bash
git add frontend/app/src/store/types.ts frontend/app/src/store/app-store.ts
git commit -m "feat(task): extend frontend types and store for cron jobs"
```

---

### Task 10: Enhance TasksPage with new fields

**Files:**
- Modify: `frontend/app/src/pages/TasksPage.tsx`

**Step 1: Add source badge to task cards/rows**

In the table row and kanban card, add a badge showing the task source:

```tsx
// Helper
const sourceLabel: Record<TaskSource, string> = {
  manual: "手动",
  cron: "定时",
  agent: "Agent",
  queue: "队列",
};

// In table row, after title column:
{task.source && task.source !== "manual" && (
  <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">
    {sourceLabel[task.source] || task.source}
  </span>
)}
```

**Step 2: Add thread_id link**

If task has `thread_id`, show a clickable link icon:

```tsx
{task.thread_id && (
  <a href={`/chat/${task.thread_id}`} className="text-muted-foreground hover:text-primary">
    <ExternalLink className="w-3.5 h-3.5" />
  </a>
)}
```

**Step 3: Add result preview in edit panel**

When task is completed and has result, show it:

```tsx
{editForm?.status === "completed" && editForm?.result && (
  <div>
    <label className="text-xs text-muted-foreground">执行结果</label>
    <p className="text-sm mt-1 p-2 bg-muted rounded">{editForm.result}</p>
  </div>
)}
```

**Step 4: Add 5-second polling**

```tsx
useEffect(() => {
  const interval = setInterval(() => {
    fetchTasks();
  }, 5000);
  return () => clearInterval(interval);
}, [fetchTasks]);
```

**Step 5: Commit**

```bash
git add frontend/app/src/pages/TasksPage.tsx
git commit -m "feat(task): enhance task cards with source badge, thread link, result preview, polling"
```

---

### Task 11: Add Cron management tab

**Files:**
- Create: `frontend/app/src/pages/CronJobsPage.tsx` (new, or inline in TasksPage)

**Step 1: Add tab switcher to TasksPage**

At the top of TasksPage, add tab buttons: `任务看板 | 定时任务`

```tsx
const [activeTab, setActiveTab] = useState<"tasks" | "cron">("tasks");
```

**Step 2: Build CronJobs view**

Reuse the same layout pattern as tasks:
- Table with columns: Name, Schedule (human-readable), Next trigger, Enabled toggle
- Edit panel on the right (same pattern)
- "新建定时任务" button
- Manual trigger button per row

For human-readable cron: use a simple `cronToHuman()` helper or the `cronstrue` npm package.

```bash
cd /Users/apple/worktrees/leon--feat-task-system/frontend/app
npm install cronstrue
```

**Step 3: Wire to store**

```tsx
const cronJobs = useAppStore(s => s.cronJobs);
const fetchCronJobs = useAppStore(s => s.fetchCronJobs);
// ... etc
```

**Step 4: Verify by starting frontend**

```bash
cd /Users/apple/worktrees/leon--feat-task-system/frontend/app
npm run dev
```

Navigate to `/tasks`, click "定时任务" tab, verify CRUD works.

**Step 5: Commit**

```bash
git add frontend/app/src/pages/TasksPage.tsx frontend/app/package.json frontend/app/package-lock.json
git commit -m "feat(task): add Cron management tab to TasksPage"
```

---

## Verification Checklist

After all tasks complete, verify end-to-end:

1. **Backend starts clean**: `uv run python -m backend.web.main` — no errors, CronService starts
2. **Cron CRUD**: Create/edit/delete cron jobs via API (`/api/panel/cron-jobs`)
3. **Cron trigger**: Manual trigger creates a task with `source=cron`
4. **Agent tools**: Start a thread, verify Agent has `ListBoardTasks` etc. in tool list
5. **Agent claim**: Create a pending task, tell Agent to claim and complete it
6. **Frontend tasks**: New fields (source, thread link) visible in UI
7. **Frontend cron**: Tab switch works, cron CRUD from UI works
8. **Polling**: Change task status from API, frontend updates within 5s
9. **All tests pass**: `uv run pytest tests/test_task_service.py tests/test_cron_job_service.py tests/test_cron_service.py tests/test_taskboard_middleware.py -v`
