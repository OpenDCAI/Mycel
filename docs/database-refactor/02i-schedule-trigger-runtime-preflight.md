# Database Refactor 02I Schedule Trigger Runtime Preflight

Date: 2026-04-14

Checkpoint:

- `database-refactor-02i-schedule-trigger-runtime-preflight`

Status:

- implemented
- proof: `docs/database-refactor/02i-schedule-trigger-runtime-proof.md`

## Goal

Add the first honest runtime path for schedule execution:

```text
agent.schedules row -> schedule_run row -> route instruction into an agent thread
```

This must not resurrect the old `cron_jobs -> panel_tasks` behavior.

## Current Usable Surfaces

From existing runtime:

- `backend.web.services.schedule_service`
  - schedule CRUD over `agent.schedules`
  - run CRUD over `agent.schedule_runs`
- `backend.web.services.message_routing.route_message_to_brain`
  - if thread agent is idle: starts an agent run
  - if thread agent is active: enqueues a steer message
  - returns routing status, run id when a new run starts, and thread id
- `backend.web.routers.threads._create_owned_thread`
  - private router helper that creates thread + sandbox resources
  - currently too coupled to reuse from schedule runtime without extraction
- `backend.web.services.cron_service.CronService`
  - legacy service that reads `cron_jobs` and creates panel tasks
  - not a valid extension point for new schedule runtime

## Product And Scope Decision

02I should be a manual trigger runtime slice, not a full scheduler.

Recommended scope:

- add explicit schedule runtime service
- add explicit authenticated schedule trigger API
- support only schedules with `target_thread_id`
- create `agent.schedule_runs` before routing
- route `instruction_template` into the target thread through `route_message_to_brain`
- update run status to `running` when routing is accepted
- update run status to `failed` when validation/routing fails
- prove no `panel_tasks` rows are created

Not in 02I:

- no cron loop
- no due schedule polling
- no `/api/panel/cron-jobs`
- no `CronService` edits
- no frontend
- no RLS/realtime
- no create-thread-on-run implementation
- no completion hook from agent run events to schedule_runs `succeeded`

## Approach Options

### Option A: Explicit Schedule Runtime Service + Manual Trigger API

New service:

- `backend/web/services/schedule_runtime_service.py`

New router:

- `backend/web/routers/schedules.py`
- `POST /api/schedules/{schedule_id}/run`

Flow:

1. Load schedule by id.
2. Verify schedule exists, is enabled, and belongs to the authenticated user.
3. Require `target_thread_id`.
4. Verify target thread exists and belongs to the schedule owner and schedule agent.
5. Create schedule run with status `queued`.
6. Route `instruction_template` into the target thread through `route_message_to_brain`.
7. Update schedule run to `running`, storing thread id and route output.
8. Update schedule `last_run_at`.
9. Return the schedule run and route result.

Failure flow:

1. If schedule is invalid or disabled, fail loudly before creating a run.
2. If target resolution/routing fails after run creation, mark run `failed`, set `completed_at`, and store `error`.

Verdict:

- recommended
- small enough to verify
- explicit new ontology
- no hidden cron compatibility

### Option B: Rewrite CronService To Trigger agent.schedule_runs

Rejected.

Problems:

- old service name and API still say cron job
- old data source is `cron_jobs`
- old effect is panel task creation
- this would encourage compatibility glue instead of schedule ontology

### Option C: Full Scheduler Runtime With create_thread_on_run

Rejected for 02I.

Problems:

- needs thread creation service extraction from router helper
- needs due polling and concurrency/locking policy
- needs run completion semantics
- too large for one bounded checkpoint

This should become later checkpoints after manual trigger proves the execution path.

## 02I Runtime/API Surface

### Service API

`backend.web.services.schedule_runtime_service`:

```python
async def trigger_schedule(
    app: Any,
    schedule_id: str,
    *,
    owner_user_id: str,
    triggered_by: str = "manual",
) -> dict[str, Any]:
    ...
```

Return shape:

```python
{
    "schedule_run": {...},
    "routing": {...},
}
```

### HTTP API

`backend.web.routers.schedules`:

```text
POST /api/schedules/{schedule_id}/run
```

Auth:

- `get_current_user_id`

Request body:

- no required fields in 02I

Response:

```python
{
    "item": {
        "schedule_run": {...},
        "routing": {...},
    }
}
```

Not added in 02I:

- schedule CRUD HTTP API
- list runs HTTP API
- frontend UI

Reason:

- 02H already proves repo/service CRUD
- 02I only needs an authenticated surface to prove trigger runtime

## Thread Steering Rule

For 02I, only this target shape is executable:

```text
target_thread_id is set
```

Validation:

- schedule owner must match authenticated user
- schedule must be enabled
- thread must exist
- thread owner must match schedule owner
- thread member/agent id must match schedule agent id

If `target_thread_id` is missing and `create_thread_on_run` is true:

- return an explicit unsupported-target error
- do not invent a thread
- do not call `_create_owned_thread`
- do not fallback to main thread

Reason:

- thread creation is currently buried in `backend.web.routers.threads._create_owned_thread`
- reusing that private router helper from runtime service would deepen coupling
- extracting thread creation into a service is a separate checkpoint

## Schedule Run Lifecycle In 02I

Supported transitions:

```text
queued -> running
queued -> failed
```

`queued`:

- created before routing
- contains schedule id, owner id, agent id, trigger source, scheduled_for/input_json

`running`:

- set after `route_message_to_brain` accepts the instruction
- includes `thread_id`
- `output_json` stores route result, such as direct start or steer injection

`failed`:

- set if target validation or routing fails after the run row exists
- sets `completed_at`
- stores error string

Not supported in 02I:

- `succeeded`
- `cancelled`
- retry
- completion based on actual LLM run outcome

Reason:

- `route_message_to_brain` starts or queues work but does not synchronously represent final LLM completion
- marking `succeeded` at route acceptance would be false evidence
- completion hook needs a later event integration checkpoint

## Instruction Payload

The message sent to the agent should be the schedule `instruction_template` plus minimal schedule context.

Proposed text:

```text
[Scheduled instruction]
Schedule ID: <schedule_id>
Schedule Run ID: <run_id>

<instruction_template>
```

Reason:

- gives the agent durable ids for logs/follow-up
- avoids legacy task-template JSON
- does not add new prompt framework

## RED/GREEN Plan

### RED 1: Runtime creates run and routes target-thread schedule

Create `tests/test_schedule_runtime_service.py`.

Fake app state:

- schedule service repo returns one schedule with `target_thread_id`
- thread repo returns matching owner/agent thread
- route function is monkeypatched to capture call and return `{"status": "started", ...}`

Expected RED:

- import fails because `schedule_runtime_service` does not exist

### RED 2: Runtime rejects create_thread_on_run without target

Test schedule:

- `target_thread_id = None`
- `create_thread_on_run = True`

Expected behavior:

- no call to `route_message_to_brain`
- run is not created, or if created after target resolution is moved earlier, run is marked failed
- recommended: fail before run creation because no execution target exists in 02I

### RED 3: HTTP API calls runtime with authenticated user

Create `tests/test_schedules_router.py`.

Test shape:

- include schedules router in a small FastAPI app
- override auth dependency to return `owner_1`
- monkeypatch runtime trigger function
- POST `/api/schedules/schedule_1/run`
- assert runtime receives `owner_user_id="owner_1"`

Expected RED:

- router does not exist

### GREEN

Implement only:

- `backend/web/services/schedule_runtime_service.py`
- `backend/web/routers/schedules.py`
- `backend/web/main.py` router registration
- focused tests

Do not touch:

- `backend/web/services/cron_service.py`
- `backend/web/routers/panel.py`
- frontend files
- schedule DDL

## Verification Plan

Focused tests:

```bash
uv run pytest tests/test_schedule_runtime_service.py tests/test_schedules_router.py -q
```

Regression pack:

```bash
uv run pytest tests/test_supabase_schedule_repo_schema.py tests/test_schedule_service_schema_contract.py tests/test_supabase_tool_task_repo_schema.py tests/test_thread_task_tool_surface_schema.py tests/test_supabase_chat_repo_schema.py -q
```

Lint/format:

```bash
uv run ruff check backend/web/services/schedule_runtime_service.py backend/web/routers/schedules.py backend/web/main.py tests/test_schedule_runtime_service.py tests/test_schedules_router.py
uv run ruff format --check backend/web/services/schedule_runtime_service.py backend/web/routers/schedules.py backend/web/main.py tests/test_schedule_runtime_service.py tests/test_schedules_router.py
```

Backend API YATU target:

1. Start real backend with Supabase runtime and real LLM API key environment.
2. Authenticate as a real test user.
3. Create or select an owned agent thread.
4. Insert a temporary schedule for that user/agent/thread through `schedule_service`.
5. Call authenticated `POST /api/schedules/{schedule_id}/run`.
6. Assert response contains a schedule run with status `running`.
7. Assert no new `public.panel_tasks` row was created.
8. Assert run row exists in `agent.schedule_runs` with route output.
9. Cleanup temporary schedule/run rows.

LLM/agent evidence bar:

- If route result is `started`, verify a real agent run was started with a real LLM key configured.
- If route result is `injected` because the agent was already active, treat it as routing proof only, not completion proof.
- Do not claim schedule execution succeeded unless a later checkpoint observes final assistant output or run event completion.

## Stopline

Stop and return to Ledger if implementation requires any of these:

- editing `/api/panel/cron-jobs`
- editing `CronService`
- creating panel tasks
- mapping `cron_jobs` to schedules
- adding frontend schedule UI
- implementing cron polling loop
- implementing create-thread-on-run
- calling private router helper `_create_owned_thread` from runtime service
- marking schedule runs `succeeded` without real completion evidence
- adding RLS/realtime/authenticated table grants

The acceptable 02I closure is:

```text
Authenticated manual trigger for target-thread schedules creates schedule_run and routes instruction into the agent thread, with no panel_tasks creation and no false completion claim.
```
