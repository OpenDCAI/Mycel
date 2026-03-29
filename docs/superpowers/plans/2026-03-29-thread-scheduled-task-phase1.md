# Thread-Bound Scheduled Task Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first backend slice of a scheduled task system that dispatches work directly into a long-lived thread and records execution runs.

**Architecture:** Add a new `backend/scheduled_tasks/` domain with explicit storage and service boundaries. Keep legacy `cron_jobs`, `panel_tasks`, and `core/tools/task` untouched in phase 1, and integrate dispatch only through the existing thread routing gateway.

**Tech Stack:** Python 3.12+, FastAPI, SQLite, croniter, pytest, existing backend runtime services.

---

### Task 1: Add Storage Tests For Scheduled Tasks

**Files:**
- Create: `tests/test_scheduled_task_service.py`
- Create: `backend/scheduled_tasks/__init__.py`
- Create: `backend/scheduled_tasks/service.py`

- [ ] **Step 1: Write the failing tests**

Write tests for:
- create scheduled task
- get/list scheduled tasks
- update scheduled task
- delete scheduled task
- create/list/update scheduled task runs

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_scheduled_task_service.py`
Expected: FAIL with import/module errors for `backend.scheduled_tasks.service`

- [ ] **Step 3: Write minimal implementation**

Implement SQLite-backed repositories and service helpers in `backend/scheduled_tasks/service.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_scheduled_task_service.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_scheduled_task_service.py backend/scheduled_tasks/__init__.py backend/scheduled_tasks/service.py
git commit -m "feat: add scheduled task storage service"
```

### Task 2: Add Scheduler Dispatch Tests

**Files:**
- Modify: `tests/test_scheduled_task_service.py`
- Create: `backend/scheduled_tasks/runtime.py`

- [ ] **Step 1: Write the failing tests**

Add tests for:
- due calculation using cron
- manual trigger creates a run and updates task timestamps
- dispatch failure marks run failed

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_scheduled_task_service.py`
Expected: FAIL with missing runtime dispatch/scheduler helpers

- [ ] **Step 3: Write minimal implementation**

Implement:
- `ScheduledTaskDispatcher`
- `ScheduledTaskScheduler`
- due calculation helper

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_scheduled_task_service.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_scheduled_task_service.py backend/scheduled_tasks/runtime.py
git commit -m "feat: add scheduled task scheduler runtime"
```

### Task 3: Add API Tests And Endpoints

**Files:**
- Create: `tests/test_scheduled_task_api.py`
- Modify: `backend/web/models/panel.py`
- Modify: `backend/web/routers/panel.py`

- [ ] **Step 1: Write the failing tests**

Add API-level tests for:
- list/create/update/delete scheduled tasks
- manual trigger endpoint
- list runs endpoint

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_scheduled_task_api.py`
Expected: FAIL because request models and endpoints do not exist

- [ ] **Step 3: Write minimal implementation**

Add request models and endpoints that call the new scheduled task service/runtime.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_scheduled_task_api.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_scheduled_task_api.py backend/web/models/panel.py backend/web/routers/panel.py
git commit -m "feat: add scheduled task panel api"
```

### Task 4: Wire Scheduler Into App Lifespan

**Files:**
- Modify: `backend/web/core/lifespan.py`
- Modify: `backend/scheduled_tasks/runtime.py`
- Modify: `tests/test_scheduled_task_service.py`

- [ ] **Step 1: Write the failing tests**

Add tests for:
- scheduler start/stop lifecycle
- manual trigger path using the same dispatch code as periodic checks

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_scheduled_task_service.py`
Expected: FAIL because lifecycle wiring does not exist

- [ ] **Step 3: Write minimal implementation**

Wire the scheduler into FastAPI lifespan using `app.state.scheduled_task_scheduler`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_scheduled_task_service.py tests/test_scheduled_task_api.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/web/core/lifespan.py backend/scheduled_tasks/runtime.py tests/test_scheduled_task_service.py
git commit -m "feat: wire scheduled task scheduler into app lifecycle"
```

### Task 5: Verify Targeted Regression Suite

**Files:**
- Test: `tests/test_scheduled_task_service.py`
- Test: `tests/test_scheduled_task_api.py`
- Test: `tests/test_cron_service.py`
- Test: `tests/test_cron_job_service.py`
- Test: `tests/test_task_service.py`

- [ ] **Step 1: Run focused regression suite**

Run:

```bash
uv run pytest -q \
  tests/test_scheduled_task_service.py \
  tests/test_scheduled_task_api.py \
  tests/test_cron_service.py \
  tests/test_cron_job_service.py \
  tests/test_task_service.py
```

Expected: PASS

- [ ] **Step 2: Inspect for accidental legacy coupling**

Confirm:
- no new writes to `panel_tasks` in scheduled task path
- no dependency on `core/tools/task`

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: verify scheduled task phase1 integration"
```
