# Thread-Bound Scheduled Task Design

## Goal

Build a backend scheduled task system that triggers work on a long-lived `thread` directly, instead of merely creating a panel task record. The scheduled task system must stay conceptually related to the broader task domain, but the first implementation phase should keep a clear boundary from legacy task surfaces such as `panel_tasks` and `core/tools/task`.

## Current State

The codebase currently has multiple task-like systems with different semantics:

- `backend/web/services/cron_job_service.py` + `backend/web/services/cron_service.py`
  - Stores cron definitions and currently creates `panel_tasks`
- `backend/web/services/task_service.py`
  - Stores panel task board records for the Web UI
- `core/tools/task/service.py`
  - Agent-facing thread-local checklist tools (`TaskCreate`, `TaskList`, etc.)
- `backend/web/routers/threads.py`
  - Exposes background run inspection endpoints for bash/agent runs

These systems are not unified. The useful existing capability for the new design is `route_message_to_brain()` in `backend/web/services/message_routing.py`, which can deliver a message into a long-lived thread:

- if thread is idle: start a run immediately
- if thread is active: enqueue into followup queue

## Non-Goals For Phase 1

- Do not unify `panel_tasks` with the new scheduled task domain
- Do not merge `core/tools/task` into the new scheduled task domain
- Do not redesign the frontend task UI
- Do not introduce an outbox/worker architecture unless necessary

## Design Principles

- Prefer the smallest maintainable model that can support direct thread execution
- Keep external boundaries clear: external callers deal with scheduled tasks and scheduled task runs, not queues or runtime internals
- Keep legacy systems stable by using adapters instead of invasive rewrites
- Fail loudly when dispatch fails; do not hide scheduler/runtime errors behind silent fallbacks

## Proposed Module Boundary

Create a new backend module:

- `backend/scheduled_tasks/`

Responsibilities:

- scheduled task definition model
- scheduled task run model
- repository layer for persistence
- scheduler service for trigger evaluation
- dispatch service that calls into thread delivery/runtime

This module becomes the only place that understands the full lifecycle:

`schedule definition -> due trigger -> run record -> thread dispatch -> run status update`

## Core Domain Objects

### ScheduledTask

A long-lived schedule definition bound to a thread.

Fields:

- `id`
- `thread_id`
- `name`
- `instruction`
- `cron_expression`
- `enabled`
- `last_triggered_at`
- `next_trigger_at`
- `created_at`
- `updated_at`

### ScheduledTaskRun

A single execution attempt created when a scheduled task fires.

Fields:

- `id`
- `scheduled_task_id`
- `thread_id`
- `status`
- `triggered_at`
- `started_at`
- `completed_at`
- `dispatch_result`
- `thread_run_id`
- `error`

Minimal status model for phase 1:

- `queued`
- `dispatched`
- `completed`
- `failed`

## Dispatch Boundary

Introduce an internal boundary interface:

- `ThreadDispatchGateway`

Input:

- `thread_id`
- `instruction`
- scheduled task run metadata

Output:

- accepted/rejected dispatch result
- optional `thread_run_id`

Implementation for phase 1:

- call `route_message_to_brain()` from `backend/web/services/message_routing.py`
- store the return payload on `ScheduledTaskRun`

The scheduler domain should not call queue manager, agent pool, or runtime state directly.

## Persistence Design

Add two SQLite-backed tables in the main backend DB:

### `scheduled_tasks`

- persistent schedule definitions

### `scheduled_task_runs`

- append-only execution log per trigger

Reasoning:

- keeps phase 1 simple
- avoids overloading `cron_jobs`
- avoids forcing new semantics into `panel_tasks`

## Execution Flow

1. Scheduler loop loads enabled scheduled tasks
2. For each task, evaluate whether it is due using cron expression and `last_triggered_at`
3. When due:
   - create a `scheduled_task_runs` record with `status=queued`
   - dispatch to thread through `ThreadDispatchGateway`
4. On successful dispatch:
   - update run to `dispatched`
   - capture returned payload, including `run_id` when available
   - update scheduled task `last_triggered_at` and `next_trigger_at`
5. On dispatch failure:
   - update run to `failed`
   - store error text
   - do not silently swallow failure

## Relationship To Legacy Task Systems

### `panel_tasks`

Phase 1 relation:

- none in the primary execution path
- optional future projection only

Why:

- `panel_tasks` currently models task board records, not direct thread execution truth
- forcing writes into `panel_tasks` now would mix scheduling semantics with UI projection semantics

### `core/tools/task`

Phase 1 relation:

- no direct dependency
- leave room for future adapter

Why:

- it behaves like an agent-local checklist system inside a thread
- it is not the same thing as a scheduled execution record

## API Shape For Phase 1

Add new endpoints under the panel API for scheduled task management:

- list scheduled tasks
- create scheduled task
- update scheduled task
- delete scheduled task
- trigger scheduled task manually
- list scheduled task runs for a scheduled task

The manual trigger path must use the same code path as the scheduler loop.

## Testing Strategy

Phase 1 tests should cover:

- repository CRUD for scheduled tasks
- repository CRUD for scheduled task runs
- due calculation for cron expressions
- dispatch success path
- dispatch failure path
- manual trigger endpoint behavior
- scheduler loop behavior without relying on real wall clock waiting

## Migration Strategy

Phase 1 should not mutate or reinterpret legacy `cron_jobs`.

Instead:

- add new tables
- add new service
- wire a new scheduler instance in app lifespan
- keep old cron code untouched until replacement is proven

## Recommendation

Implement phase 1 as a clean new module with explicit boundaries. Do not retrofit direct thread dispatch into `cron_jobs` or `panel_tasks`.
