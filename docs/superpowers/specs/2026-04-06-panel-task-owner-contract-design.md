# Panel Task Owner Contract Design

**Date:** 2026-04-06
**Branch:** `code-killer-phase-2`

## Goal

Tighten the owner-scoping contract for panel task and cron-job APIs without widening into runtime, display/streaming, or Supabase factory work.

## Scope

This design only covers:

- `backend/web/routers/panel.py`
- `backend/web/services/task_service.py`
- `backend/web/services/cron_job_service.py`
- `backend/web/services/cron_service.py`
- `storage/providers/supabase/panel_task_repo.py`
- `storage/providers/supabase/cron_job_repo.py`
- focused tests for these paths

This design explicitly does **not** cover:

- runtime/message routing/checkpointer
- display/history/SSE surfaces
- provider/sandbox contracts
- Supabase client factory or lifespan wiring
- monitor/resource issue-205 work

## Problem

The panel owner contract is currently inconsistent.

Facts from the current tree:

- task `list/create` paths pass `owner_user_id=user_id`
- task `bulk-status / bulk-delete / update / delete` do not pass owner scope
- cron `list/create` paths pass `owner_user_id=user_id`
- cron `update / delete / run` do not carry owner scope
- `CronService.trigger_job()` fetches a job without owner scope and creates a task without preserving the job's `owner_user_id`
- task/cron repos only expose owner filtering on `list_all()`, so write paths cannot be owner-honest even if routers want to be

This is not only duplicate wiring noise. It is a real contract drift: some panel paths are tenant-aware and some are effectively global-by-id.

## Chosen Approach

Use a narrow contract-alignment pass:

1. Make owner scope explicit on all panel task/cron write paths.
2. Push that scope through service functions instead of duplicating ad-hoc checks in routers.
3. Teach the Supabase task/cron repos to perform owner-scoped get/update/delete/bulk operations.
4. Preserve cron-trigger semantics by copying `owner_user_id` from the cron job into the created task.

This keeps the simplification honest:

- less repeated “sometimes owner-aware, sometimes not” wiring
- clearer service/repo contracts
- no fake generic CRUD abstraction

## Alternatives Considered

### 1. Router-only owner checks

Rejected.

This would keep service/repo contracts dishonest and leave `CronService.trigger_job()` outside the safety boundary.

### 2. Generic shared panel CRUD owner helper

Rejected.

This compresses task and cron semantics into one helper layer just to save lines. It would trade visible duplication for a less honest abstraction.

### 3. Recommended: explicit owner contract alignment

Accepted.

It is small enough for one PR and actually reduces semantic drift instead of just moving code around.

## Intended Code Shape

### Router layer

`panel.py` remains thin:

- read `user_id`
- pass `owner_user_id=user_id` to every task/cron mutation and lookup path
- keep HTTP mapping local (`404`, `403` only if returned shape demands it)

### Service layer

`task_service.py` and `cron_job_service.py` become owner-honest:

- `get_*`, `update_*`, `delete_*`, and task bulk mutations accept `owner_user_id`
- service signatures make the owner requirement visible to callers
- existing list/create behavior stays intact

### Repo layer

Supabase repos get the minimum new surface needed:

- task repo:
  - `get(task_id, owner_user_id=None)`
  - `update(task_id, owner_user_id=None, **fields)`
  - `delete(task_id, owner_user_id=None)`
  - `bulk_delete(ids, owner_user_id=None)`
  - `bulk_update_status(ids, status, owner_user_id=None)`
- cron repo:
  - `get(job_id, owner_user_id=None)`
  - `update(job_id, owner_user_id=None, **fields)`
  - `delete(job_id, owner_user_id=None)`

Filtering stays at the data layer with `eq("owner_user_id", owner_user_id)` when provided.

### Cron trigger path

`CronService.trigger_job()` should:

- fetch the job with owner scope when a caller provides one
- preserve job ownership by passing `owner_user_id=job.get("owner_user_id")` into `task_service.create_task()`

## Testing Strategy

Use TDD and keep tests focused.

### Focused regressions

Add a new targeted test file for owner-contract behavior:

- panel task mutation routes pass `owner_user_id` through
- panel cron mutation routes pass `owner_user_id` through
- cron trigger creates a task under the cron job's owner

### Verification

Minimum proof for this seam:

- focused pytest file for the new owner-contract tests
- existing `tests/Fix/test_panel_auth_shell_coherence.py`
- `frontend/app npm run build`
- `python3 -m py_compile` on touched backend modules

If broader tests become necessary, add them only when a real regression demands them.

## Stopline

This PR stops at owner-contract alignment plus the small simplification that falls out of it.

It must **not** expand into:

- generic panel infrastructure
- display/streaming cleanup
- monitor/resource refactors
- runtime or provider seams
