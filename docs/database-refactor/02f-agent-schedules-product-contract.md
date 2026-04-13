# Database Refactor 02F Agent Schedules Product Contract

Date: 2026-04-14

Checkpoint:

- `database-refactor-02f-agent-schedules-product-contract-ruling`

Status:

- design/preflight only
- no implementation
- no DDL
- no runtime behavior change

## Boundary

02F covers only the future product/schema contract for:

- `agent.schedules`
- `agent.schedule_runs`

It does not cover:

- `panel_tasks`
- `agent.thread_tasks`
- background bash/agent runs
- long-running tool execution progress
- frontend Tasks page redesign
- cron UI polish
- legacy `public.cron_jobs` compatibility migration

## Live Metadata

Verified against the live Supabase REST surface using service-role credentials. Secrets were not printed.

Observed on 2026-04-14:

```text
public.cron_jobs: rows=0
staging.cron_jobs: rows=0
public.panel_tasks: rows=2
staging.panel_tasks: missing
```

Meaning:

- there is no schedule data that needs urgent preservation
- legacy panel task data exists, but panel tasks are not part of the target schedule ontology
- schedule migration is primarily a product/runtime contract decision, not a data-copy operation

## Current Runtime Shape

Current code is cron/panel-task-shaped:

- `storage/providers/supabase/cron_job_repo.py`
  - targets `cron_jobs`
  - CRUD shape: `name`, `description`, `cron_expression`, `task_template`, `enabled`, `last_run_at`, `next_run_at`, `created_at`
- `backend/web/services/cron_job_service.py`
  - thin CRUD wrapper around cron job repo
- `backend/web/services/cron_service.py`
  - parses cron expressions with `croniter`
  - `trigger_job()` loads a cron job and creates a legacy panel task through `backend.web.services.task_service`
  - updates `last_run_at`
- `backend/web/routers/panel.py`
  - exposes `/cron-jobs` CRUD and `/cron-jobs/{job_id}/run`
- `frontend/app/src/store/types.ts`
  - has legacy `CronJob` and panel `Task` types
- `tests/test_cron_service.py`
  - currently asserts that triggering a cron job creates a panel task

This runtime shape is not compatible with directly creating `agent.schedules` DDL, because doing so would either preserve panel tasks by inertia or introduce `schedule_runs` without a clear execution lifecycle.

## Option Comparison

### Option A: Agent Schedule Steers Or Creates Agent Thread

Contract:

- a schedule belongs to an owner user
- a schedule targets an agent user
- a schedule either creates a new agent thread or steers an existing configured thread
- every firing creates an `agent.schedule_runs` row
- run outcome is visible through schedule run history

Advantages:

- aligns with the database refactor target: schedules are agent runtime primitives
- avoids legacy panel task preservation
- gives `schedule_runs` a real lifecycle
- supports future Mycel-agent self-development loops

Costs:

- requires a precise target for thread selection and message/steer payload
- requires a new schedule run lifecycle
- requires backend runtime behavior changes
- frontend legacy Tasks/Cron UI cannot be treated as semantically correct without redesign or compatibility translation

Verdict:

- chosen target direction
- not authorized for implementation in 02F

### Option B: Compatibility UI Label, Backend Reroutes To Agent Schedule

Contract:

- keep `/cron-jobs` and UI labels temporarily
- backend stores target records in `agent.schedules`
- `/cron-jobs/{id}/run` triggers agent schedule execution instead of panel task creation

Advantages:

- minimizes immediate frontend churn
- can keep user-facing affordance while backend ontology changes

Costs:

- high risk of semantic confusion
- API name says cron job while storage/runtime says agent schedule
- easy to hide a compatibility fallback behind old names

Verdict:

- allowed only as a future compatibility shim if explicitly designed
- should not be the core ontology

### Option C: Park Schedule Runtime

Contract:

- do not create schedule tables yet
- remove or hide schedule runtime until a real product loop exists

Advantages:

- lowest risk
- avoids half-designed scheduler semantics

Costs:

- does not advance schedule capability
- leaves legacy `/cron-jobs` code in place

Verdict:

- acceptable if Option A cannot be made precise
- not the preferred direction because schedules are part of the target schema plan

## Chosen Contract

Choose Option A as the target contract:

```text
agent.schedule -> agent thread execution -> agent.schedule_run
```

Minimum schedule relation:

- `owner_user_id`
- `agent_user_id`
- `target_thread_id` nullable
- `create_thread_on_run` boolean
- `cron_expression`
- `enabled`
- `instruction_template`
- `timezone`
- `last_run_at`
- `next_run_at`
- `created_at`
- `updated_at`

Thread targeting rule:

- if `target_thread_id` is set, a run steers that thread
- if `target_thread_id` is not set and `create_thread_on_run` is true, a run creates a new thread for `agent_user_id`
- if neither is true, the schedule is invalid and must fail loudly before execution

Instruction template rule:

- the schedule payload is an instruction to the agent, not a panel-task template
- old panel task fields such as `priority`, `assignee_id`, `deadline`, and panel tags are not target schedule fields
- if a compatibility UI submits old task-template JSON, a future compatibility layer must translate it explicitly or reject it

## Schedule Run Lifecycle

Minimum `agent.schedule_runs` states:

```text
queued
running
succeeded
failed
cancelled
```

Minimum run fields:

- `id`
- `schedule_id`
- `owner_user_id`
- `agent_user_id`
- `thread_id`
- `status`
- `triggered_by`
- `scheduled_for`
- `started_at`
- `completed_at`
- `input_json`
- `output_json`
- `error`
- `created_at`

`triggered_by` values:

- `scheduler`
- `manual`

Retry/cancel stance:

- no retry semantics in the first implementation slice
- no durable cancel semantics in the first implementation slice unless the execution path already exposes one cleanly
- failed runs record `error` and stop

## Rejected Legacy Concepts

Do not migrate or preserve these into the target schedule model:

- `panel_tasks`
- panel task `priority`
- panel task `assignee_id`
- panel task `deadline`
- panel task progress
- old panel task result fields
- `cron_job_id` as a panel task linkage

Do not treat `agent.thread_tasks` as schedule output.

`agent.thread_tasks` remains the thread-scoped Task tool work list. A schedule run may cause an agent to use Task tools later, but that is agent behavior, not the schedule storage contract.

## Future Implementation Slices

### 02G: Agent Schedule DDL Precheck And Migration

Scope:

- create `agent.schedules`
- create `agent.schedule_runs`
- grant service-role access
- no deletion/mutation of `public.*` or `staging.*`
- no runtime route change yet

Verification:

- live metadata precheck
- migration execution proof
- information_schema proof
- service-role REST proof

### 02H: Schedule Repo Routing

Scope:

- route Supabase schedule repo to `agent.schedules`
- introduce explicit schedule repo naming if needed
- preserve old `/cron-jobs` route only if compatibility is explicitly accepted

Verification:

- RED/GREEN repo schema tests
- no fallback to `cron_jobs`
- real service-role CRUD proof with cleanup

### 02I: Schedule Trigger Runtime

Scope:

- make manual/scheduler trigger create `agent.schedule_runs`
- steer existing thread or create a thread according to the contract
- stop creating panel tasks

Verification:

- backend API or strongest available runtime proof
- schedule run state transition proof
- no panel task row creation

### Later: Frontend Schedule UX

Scope:

- redesign UI language from cron/panel task to agent schedule
- or explicitly define compatibility UI behavior

Verification:

- Playwright CLI frontend YATU only

## Risk / Size

Expected future implementation size:

- DDL slice: small-to-medium
- repo routing slice: small
- runtime trigger slice: medium-to-high
- frontend UX slice: high if done properly

Primary risks:

- preserving panel tasks by inertia
- creating `schedule_runs` without a run lifecycle
- pretending `/cron-jobs` is already semantically correct
- mixing schedule output with `agent.thread_tasks`
- adding compatibility fallback instead of a clear translation boundary

## 02F Closure Evidence

02F only closes the product contract ruling.

Evidence:

- source inspection of current cron repo/service/router/frontend/tests
- live metadata count proof for `cron_jobs` and `panel_tasks`
- explicit option comparison
- selected target contract
- future implementation slice boundaries

No code, DDL, runtime behavior, frontend, or database state changed for 02F.
