# Panel Task Owner Contract Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make panel task and cron-job routes owner-honest end to end, while keeping the change limited to router/service/repo wiring.

**Architecture:** Pass `owner_user_id` through every panel task/cron mutation path, teach the service layer to require and forward that contract, and let the Supabase repos enforce the scope in query space. Keep the router thin and avoid introducing generic CRUD helpers.

**Tech Stack:** FastAPI, asyncio `to_thread`, Supabase repos, pytest

---

### Task 1: Write focused owner-contract regressions

**Files:**
- Create: `tests/Fix/test_panel_task_owner_contract.py`
- Read: `backend/web/routers/panel.py`
- Read: `backend/web/services/cron_service.py`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.web.models.panel import BulkDeleteTasksRequest, BulkTaskStatusRequest, UpdateCronJobRequest, UpdateTaskRequest
from backend.web.routers import panel as panel_router
from backend.web.services.cron_service import CronService


@pytest.mark.asyncio
async def test_panel_task_mutations_forward_owner_scope(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, tuple] = {}

    monkeypatch.setattr(
        panel_router.task_service,
        "bulk_update_task_status",
        lambda ids, status, owner_user_id=None: seen.setdefault("bulk_status", (ids, status, owner_user_id)) or len(ids),
    )
    monkeypatch.setattr(
        panel_router.task_service,
        "bulk_delete_tasks",
        lambda ids, owner_user_id=None: seen.setdefault("bulk_delete", (ids, owner_user_id)) or len(ids),
    )
    monkeypatch.setattr(
        panel_router.task_service,
        "update_task",
        lambda task_id, owner_user_id=None, **fields: seen.setdefault("update", (task_id, owner_user_id, fields)) or {"id": task_id},
    )
    monkeypatch.setattr(
        panel_router.task_service,
        "delete_task",
        lambda task_id, owner_user_id=None: seen.setdefault("delete", (task_id, owner_user_id)) or True,
    )

    await panel_router.bulk_update_status(BulkTaskStatusRequest(ids=["t-1"], status="completed"), user_id="user-1")
    await panel_router.bulk_delete_tasks(BulkDeleteTasksRequest(ids=["t-2"]), user_id="user-1")
    await panel_router.update_task("t-3", UpdateTaskRequest(title="new"), user_id="user-1")
    await panel_router.delete_task("t-4", user_id="user-1")

    assert seen["bulk_status"] == (["t-1"], "completed", "user-1")
    assert seen["bulk_delete"] == (["t-2"], "user-1")
    assert seen["update"][0:2] == ("t-3", "user-1")
    assert seen["delete"] == ("t-4", "user-1")


@pytest.mark.asyncio
async def test_panel_cron_mutations_forward_owner_scope(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, tuple] = {}

    monkeypatch.setattr(
        panel_router.cron_job_service,
        "update_cron_job",
        lambda job_id, owner_user_id=None, **fields: seen.setdefault("update", (job_id, owner_user_id, fields)) or {"id": job_id},
    )
    monkeypatch.setattr(
        panel_router.cron_job_service,
        "delete_cron_job",
        lambda job_id, owner_user_id=None: seen.setdefault("delete", (job_id, owner_user_id)) or True,
    )

    cron_service = SimpleNamespace(trigger_job=lambda job_id, owner_user_id=None: {"id": "task-1", "job_id": job_id, "owner_user_id": owner_user_id})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(cron_service=cron_service)))

    await panel_router.update_cron_job("job-1", UpdateCronJobRequest(description="desc"), user_id="user-1")
    await panel_router.delete_cron_job("job-2", user_id="user-1")
    result = await panel_router.trigger_cron_job("job-3", request=request, user_id="user-1")

    assert seen["update"][0:2] == ("job-1", "user-1")
    assert seen["delete"] == ("job-2", "user-1")
    assert result["item"]["owner_user_id"] == "user-1"


@pytest.mark.asyncio
async def test_cron_trigger_copies_job_owner_to_created_task(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "backend.web.services.cron_service.cron_job_service.get_cron_job",
        lambda job_id, owner_user_id=None: {
            "id": job_id,
            "enabled": 1,
            "owner_user_id": "owner-7",
            "task_template": "{\"title\":\"From cron\"}",
        },
    )

    created: dict[str, object] = {}

    monkeypatch.setattr(
        "backend.web.services.cron_service.task_service.create_task",
        lambda **fields: created.update(fields) or {"id": "task-1", **fields},
    )
    monkeypatch.setattr(
        "backend.web.services.cron_service.cron_job_service.update_cron_job",
        lambda *_args, **_kwargs: {"id": "job-1"},
    )

    task = await CronService().trigger_job("job-1")

    assert task is not None
    assert created["owner_user_id"] == "owner-7"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/Fix/test_panel_task_owner_contract.py -q`
Expected: FAIL because current panel task/cron mutation paths do not consistently pass `owner_user_id`.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/Fix/test_panel_task_owner_contract.py
git commit -m "test: cover panel owner contract drift"
```

### Task 2: Align router and service contracts

**Files:**
- Modify: `backend/web/routers/panel.py`
- Modify: `backend/web/services/task_service.py`
- Modify: `backend/web/services/cron_job_service.py`

- [ ] **Step 1: Make the task router pass owner scope everywhere**

```python
count = await asyncio.to_thread(task_service.bulk_update_task_status, req.ids, req.status, owner_user_id=user_id)
count = await asyncio.to_thread(task_service.bulk_delete_tasks, req.ids, owner_user_id=user_id)
item = await asyncio.to_thread(task_service.update_task, task_id, owner_user_id=user_id, **req.model_dump())
ok = await asyncio.to_thread(task_service.delete_task, task_id, owner_user_id=user_id)
```

- [ ] **Step 2: Make the cron router pass owner scope everywhere**

```python
job = await asyncio.to_thread(cron_job_service.update_cron_job, job_id, owner_user_id=user_id, **fields)
ok = await asyncio.to_thread(cron_job_service.delete_cron_job, job_id, owner_user_id=user_id)
task = await cron_service.trigger_job(job_id, owner_user_id=user_id)
```

- [ ] **Step 3: Make service signatures owner-honest**

```python
def get_task(task_id: str, owner_user_id: str | None = None) -> dict[str, Any] | None:
    ...
    return repo.get(task_id, owner_user_id=owner_user_id)

def update_task(task_id: str, owner_user_id: str | None = None, **fields: Any) -> dict[str, Any] | None:
    ...

def delete_task(task_id: str, owner_user_id: str | None = None) -> bool:
    ...

def bulk_delete_tasks(ids: list[str], owner_user_id: str | None = None) -> int:
    ...

def bulk_update_task_status(ids: list[str], status: str, owner_user_id: str | None = None) -> int:
    ...
```

Apply the same pattern in `cron_job_service.py` for `get/update/delete`.

- [ ] **Step 4: Run tests to verify green**

Run: `uv run pytest tests/Fix/test_panel_task_owner_contract.py -q`
Expected: PASS

- [ ] **Step 5: Commit router/service alignment**

```bash
git add backend/web/routers/panel.py backend/web/services/task_service.py backend/web/services/cron_job_service.py tests/Fix/test_panel_task_owner_contract.py
git commit -m "fix: align panel owner scope through services"
```

### Task 3: Align repo filtering and cron-trigger ownership

**Files:**
- Modify: `storage/providers/supabase/panel_task_repo.py`
- Modify: `storage/providers/supabase/cron_job_repo.py`
- Modify: `backend/web/services/cron_service.py`

- [ ] **Step 1: Add owner-aware repo methods**

```python
def get(self, task_id: str, owner_user_id: str | None = None) -> dict[str, Any] | None:
    query = self._table().select("*").eq("id", task_id)
    if owner_user_id is not None:
        query = query.eq("owner_user_id", owner_user_id)
```

Apply the same filter shape to:

- task repo `update/delete/bulk_delete/bulk_update_status`
- cron repo `get/update/delete`

- [ ] **Step 2: Preserve owner on cron-triggered tasks**

```python
async def trigger_job(self, job_id: str, owner_user_id: str | None = None) -> dict[str, Any] | None:
    job = await asyncio.to_thread(cron_job_service.get_cron_job, job_id, owner_user_id=owner_user_id)
    ...
    task_fields["owner_user_id"] = job.get("owner_user_id")
    task = await asyncio.to_thread(task_service.create_task, **task_fields)
```

- [ ] **Step 3: Run focused verification**

Run: `uv run pytest tests/Fix/test_panel_task_owner_contract.py tests/Fix/test_panel_auth_shell_coherence.py -q`
Expected: PASS

- [ ] **Step 4: Run seam-level sanity checks**

Run: `python3 -m py_compile backend/web/routers/panel.py backend/web/services/task_service.py backend/web/services/cron_job_service.py backend/web/services/cron_service.py storage/providers/supabase/panel_task_repo.py storage/providers/supabase/cron_job_repo.py`
Expected: exit 0

Run: `cd frontend/app && npm run build`
Expected: PASS

- [ ] **Step 5: Commit repo + cron alignment**

```bash
git add backend/web/services/cron_service.py storage/providers/supabase/panel_task_repo.py storage/providers/supabase/cron_job_repo.py
git commit -m "fix: enforce owner scope in panel task repos"
```

### Task 4: Final verification and PR prep

**Files:**
- Modify: `docs/superpowers/specs/2026-04-06-panel-task-owner-contract-design.md`
- Modify: `docs/superpowers/plans/2026-04-06-panel-task-owner-contract-alignment.md`

- [ ] **Step 1: Run the final branch proof**

Run: `uv run pytest tests/Fix/test_panel_task_owner_contract.py tests/Fix/test_panel_auth_shell_coherence.py -q`
Expected: PASS

Run: `cd frontend/app && npm run build`
Expected: PASS

Run: `python3 -m py_compile backend/web/routers/panel.py backend/web/services/task_service.py backend/web/services/cron_job_service.py backend/web/services/cron_service.py storage/providers/supabase/panel_task_repo.py storage/providers/supabase/cron_job_repo.py`
Expected: exit 0

- [ ] **Step 2: Update docs with any scope adjustments discovered during implementation**

Keep the stopline explicit:

- panel/task owner contract only
- no generic panel abstraction
- no runtime/display/provider spillover

- [ ] **Step 3: Commit final docs and verification-ready state**

```bash
git add docs/superpowers/specs/2026-04-06-panel-task-owner-contract-design.md docs/superpowers/plans/2026-04-06-panel-task-owner-contract-alignment.md
git commit -m "docs: capture panel owner-contract phase-2 seam"
```
