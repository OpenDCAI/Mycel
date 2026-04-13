# Database Refactor 02J Schedule Run Completion Preflight

Date: 2026-04-14

Checkpoint:

- `database-refactor-02j-schedule-run-completion`

Status:

- implemented
- proof: `docs/database-refactor/02j-schedule-run-completion-proof.md`

## Goal

Make accepted schedule triggers complete honestly:

```text
agent.schedule_runs.running -> agent.schedule_runs.succeeded | failed
```

02I proved schedule runtime entry. 02J should prove completion semantics for the only schedule trigger shape that has a clean ownership boundary:

```text
target-thread schedule -> newly-started runtime run_id -> _run_agent_to_buffer final boundary
```

## Source Proof

### Direct Start Path

`backend.web.services.message_routing.route_message_to_brain` currently has two routing outcomes:

- IDLE target agent:
  - transitions the agent runtime to `ACTIVE`
  - calls `start_agent_run(...)`
  - returns `{status: "started", routing: "direct", run_id, thread_id}`
- ACTIVE target agent:
  - enqueues a steer message
  - returns `{status: "injected", routing: "steer", thread_id}`

Only the direct-start path gives the schedule runtime a distinct runtime `run_id`.

### Runtime Final Boundary

`backend.web.services.streaming_service._run_agent_to_buffer(...)` is the real runtime run boundary:

- emits `run_start`
- streams LLM/tool events
- emits `run_done` on normal completion
- emits `cancelled` + `run_done` on cancellation
- emits `error` + `run_done` on exception
- transitions the runtime back to `IDLE` in `finally`
- starts follow-up queue consumption after cleanup

This is the right place to finalize `agent.schedule_runs`, because route acceptance is not completion.

### Current Metadata Gap

02I stores the schedule run id in the prompt text:

```text
Schedule Run ID: <run_id>
```

That is not a machine contract. 02J must carry `schedule_run_id` as structured metadata to `_run_agent_to_buffer`.

`start_agent_run(...)` already accepts `message_metadata` and passes it into `_run_agent_to_buffer(...)`.

So the intended metadata path is:

```text
schedule_runtime_service
  -> route_message_to_brain(..., message_metadata={schedule_run_id})
  -> start_agent_run(..., message_metadata=merged_metadata)
  -> _run_agent_to_buffer(..., message_metadata)
  -> schedule completion update
```

## Key Invariant

Every accepted schedule trigger in 02J must map to exactly one newly-started runtime `run_id`.

Therefore schedule triggers must be start-only in 02J:

- if the target agent is idle and `route_message_to_brain` starts a run, accept and finalize later
- if the target agent is active, reject with an explicit conflict before creating a durable `schedule_run`
- do not inject schedule instructions into an already-running agent turn

Reason:

- active injection has no distinct runtime run ownership
- expanding queue/message metadata to track injected schedule messages is a separate cross-cutting design
- marking injected schedule runs as succeeded would be false completion

## Recommended Scope

### 1. Add Start-Only Routing

Modify `route_message_to_brain` with an explicit option, for example:

```python
async def route_message_to_brain(
    app: Any,
    thread_id: str,
    content: str,
    source: str = "owner",
    ...,
    require_new_run: bool = False,
    extra_message_metadata: dict[str, Any] | None = None,
) -> dict:
    ...
```

Behavior:

- if `require_new_run=True` and the agent is already `ACTIVE`, return a loud structured conflict or raise a specific exception
- do not enqueue
- do not create a `schedule_run` before this condition is known

Preferred implementation shape:

- introduce a small exception class in `message_routing.py`, e.g. `TargetThreadActiveError`
- schedule runtime maps it to HTTP `409 Conflict`

### 2. Move Schedule Run Creation After Start-Only Eligibility

02I currently creates the schedule run before calling `route_message_to_brain`.

02J should first prove the target can accept a new direct run, then create the schedule run, then call the direct-start route.

But this has a race: the target could become active between the eligibility check and `start_agent_run`.

Better option:

- `route_message_to_brain(require_new_run=True, prepare_metadata=...)` should own the active check and direct-start atomic transition.
- schedule runtime still needs the schedule run id before `start_agent_run` so metadata can include it.

Practical 02J solution:

1. Validate schedule and target thread before creating a run.
2. Create `agent.schedule_runs` as `queued`.
3. Call `route_message_to_brain(... require_new_run=True, extra_message_metadata={"schedule_run_id": run["id"]})`.
4. If route raises `TargetThreadActiveError`, delete or cancel the just-created schedule run?

This is the tricky part. Deleting would hide the attempted trigger; cancelling would create a schedule run despite the desired no-run conflict proof.

Recommended stricter solution:

- add a schedule-runtime-local precheck for active target before run creation
- call `route_message_to_brain(require_new_run=True)` to guard the race
- if the race still loses after run creation, mark the newly-created run `cancelled` with an explicit error

YATU proof should cover the common active-before-create path and assert no `schedule_run` is created. Race fallback exists only for correctness under concurrency and should not be treated as the normal product behavior.

### 3. Carry Runtime Metadata

`route_message_to_brain` should merge `extra_message_metadata` into the `meta` dict passed to `start_agent_run`.

The resulting initial `HumanMessage` metadata should include:

```python
{
    "source": "schedule",
    "schedule_run_id": "<agent.schedule_runs.id>",
}
```

The `schedule_run_id` must not be parsed from text.

### 4. Finalize At Runtime Boundary

Add a small schedule finalization helper, probably in a new file:

- `backend/web/services/schedule_run_completion_service.py`

Suggested API:

```python
def complete_schedule_run_from_runtime(
    schedule_run_id: str | None,
    *,
    status: Literal["succeeded", "failed", "cancelled"],
    runtime_run_id: str,
    thread_id: str,
    error: str | None = None,
) -> None:
    ...
```

Behavior:

- if `schedule_run_id` is missing, no-op
- if present, update `agent.schedule_runs`
- on success:
  - `status="succeeded"`
  - `completed_at=now`
  - merge `output_json.runtime_run_id`
  - merge `output_json.thread_id`
- on failure:
  - `status="failed"` or `cancelled`
  - `completed_at=now`
  - `error=<runtime error or cancellation message>`
  - merge runtime metadata into `output_json`

This helper keeps schedule-specific persistence out of the main streaming loop body.

### 5. Wire `_run_agent_to_buffer`

Inside `_run_agent_to_buffer`:

- maintain a local terminal status:
  - success if the stream loop reaches normal `run_done`
  - cancelled on `asyncio.CancelledError`
  - failed on generic exception
- after emitting terminal event, call the completion helper with `message_metadata.get("schedule_run_id")`
- do not mark success before the agent stream actually reaches normal terminal path

Important:

- if the stream emits an `"error"` event from a non-retryable stream error and then breaks without raising, that must be treated as failed, not succeeded
- this may require setting `terminal_error` when `stream_err` is non-retryable

## Explicit Non-Scope

Not in 02J:

- no scheduler loop
- no due polling
- no cron compatibility
- no `/api/panel/cron-jobs`
- no `CronService`
- no frontend
- no schedule CRUD HTTP API
- no `create_thread_on_run`
- no active-injection completion attribution
- no DDL unless source inspection proves `output_json.runtime_run_id` is inadequate

## Proposed Write Set

Likely files:

- modify `backend/web/services/message_routing.py`
- modify `backend/web/services/schedule_runtime_service.py`
- create `backend/web/services/schedule_run_completion_service.py`
- modify `backend/web/services/streaming_service.py`
- modify `tests/test_schedule_runtime_service.py`
- create `tests/test_schedule_run_completion_service.py`
- modify or create focused tests for `message_routing` start-only behavior
- modify focused streaming tests, likely `tests/test_storage_runtime_wiring.py` or a new `tests/test_schedule_run_completion_streaming.py`
- create `docs/database-refactor/02j-schedule-run-completion-proof.md` after implementation

Avoid touching:

- `backend/web/services/cron_service.py`
- panel task repos
- frontend files
- migrations

## RED/GREEN Plan

### RED 1: Start-Only Routing

Test:

- active target + `require_new_run=True` does not enqueue
- raises/returns conflict

Expected RED:

- current `route_message_to_brain` enqueues and returns injected

### RED 2: Schedule Runtime Rejects Active Target Before Run Creation

Test:

- fake app has active agent for the target thread
- `trigger_schedule(...)` returns/raises conflict
- `create_schedule_run` is not called

Expected RED:

- current 02I creates a run and routes injected/started based on router behavior

### RED 3: Runtime Metadata Carries Schedule Run ID

Test:

- schedule runtime creates run
- route call receives `extra_message_metadata={"schedule_run_id": run_id}`
- direct route returns runtime `run_id`
- schedule run output stores runtime run id

Expected RED:

- current route has no metadata parameter

### RED 4: Completion Helper Updates Schedule Run

Test:

- `complete_schedule_run_from_runtime(schedule_run_id, status="succeeded", runtime_run_id=..., thread_id=...)`
- calls `schedule_service.update_schedule_run` with `status="succeeded"`, `completed_at`, and merged output JSON

Expected RED:

- helper does not exist

### RED 5: Streaming Final Boundary Calls Completion Helper

Test:

- run `_run_agent_to_buffer(...)` with `message_metadata={"schedule_run_id": "sr_1"}`
- fake agent stream completes normally
- completion helper receives `status="succeeded"` and runtime `run_id`

Expected RED:

- current streaming service never finalizes schedule runs

## Backend API YATU Plan

Use the same real proof shape as 02I:

1. Start backend on a temporary port with Supabase runtime env.
2. Login with existing full OTP test account.
3. Pick a target owned thread that is idle.
4. Insert temporary `agent.schedules`.
5. Call authenticated `POST /api/schedules/{schedule_id}/run`.
6. Confirm immediate response:
   - `schedule_run.status` starts as `running`
   - routing is `started/direct`
   - routing has runtime `run_id`
7. Poll `agent.schedule_runs` until:
   - `status="succeeded"`
   - `completed_at` non-null
   - `output_json.routing.run_id` or `output_json.runtime_run_id` matches route runtime run id
8. Confirm target thread has a real assistant reply.
9. Confirm `public.panel_tasks` count does not change.
10. Cleanup temporary schedule/run rows to zero.

Active conflict YATU:

1. Trigger a schedule against a target thread while its agent is active, or use a deterministic backend-level setup if real active timing is too brittle.
2. Call authenticated `POST /api/schedules/{schedule_id}/run`.
3. Expect HTTP `409 Conflict`.
4. Confirm no new `agent.schedule_runs` row was created for that schedule.

If real active timing is too brittle for product-level YATU, use focused mechanism-level proof for active conflict and say so. Do not fake it as YATU.

## Acceptance Bar

02J can close only if:

- Ledger accepts this preflight before implementation
- RED failures are captured first
- focused tests pass
- relevant regression pack passes
- ruff and format pass
- backend API YATU proves `running -> succeeded` after real runtime completion
- active target conflict is proven without creating normal schedule_run rows
- `public.panel_tasks` remains unchanged
- temporary rows are cleaned to zero

## Risk Notes

The highest-risk part is `_run_agent_to_buffer` terminal status classification.

The implementation must not mark a schedule run `succeeded` if:

- the agent stream emitted a terminal error event
- the run was cancelled
- route only injected into an active run
- no distinct runtime `run_id` exists

If this cannot be done cleanly, the correct outcome is to stop and report a runtime architecture blocker.
