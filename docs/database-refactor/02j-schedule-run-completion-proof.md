# Database Refactor 02J Schedule Run Completion Proof

Date: 2026-04-14

Checkpoint:

- `database-refactor-02j-schedule-run-completion`

Status:

- implementation proof
- ready for Ledger closure review

## Scope Landed

02J adds honest completion semantics for schedule-triggered direct runtime runs:

```text
agent.schedule_runs.running -> succeeded | failed | cancelled
```

Implemented surfaces:

- `backend.web.services.message_routing.TargetThreadActiveError`
- `route_message_to_brain(... require_new_run=True, extra_message_metadata=...)`
- `backend.web.services.schedule_runtime_service.TargetThreadBusyError`
- direct-start-only schedule trigger behavior
- `backend.web.services.schedule_run_completion_service`
- `schedule_service.get_schedule_run`
- `_run_agent_to_buffer` finalization of schedule runs at the real runtime terminal boundary
- `POST /api/schedules/{schedule_id}/run` maps active target conflicts to HTTP `409`

## Explicit Stopline Held

Not implemented:

- no scheduler loop
- no due polling
- no cron compatibility
- no `/api/panel/cron-jobs`
- no `CronService`
- no frontend
- no schedule CRUD HTTP API
- no `create_thread_on_run`
- no active-injection attribution
- no DDL
- no `panel_tasks` writes

## Design Invariant

Every accepted schedule trigger in 02J maps to exactly one newly-started runtime `run_id`.

Therefore:

- idle target: accepted, direct runtime run starts, schedule run is finalized later
- active target: rejected with `409 Conflict`, no normal schedule run is created
- race-lost-after-create path: the created run is marked `cancelled`, not hidden

## RED Evidence

Focused RED tests were added before implementation:

```text
uv run pytest tests/test_message_routing_schedule_start_only.py tests/test_schedule_runtime_service.py tests/test_schedule_run_completion_service.py tests/test_schedule_run_completion_streaming.py -q
```

First valid RED:

```text
ImportError: cannot import name 'schedule_run_completion_service' from 'backend.web.services'
```

Initial test self-check:

- a nested-class `NameError` in `tests/test_schedule_run_completion_streaming.py` was corrected before accepting RED
- after correction, RED was the missing production service, not a test typo

## GREEN Evidence

Focused 02J pack:

```text
uv run pytest tests/test_message_routing_schedule_start_only.py tests/test_schedule_runtime_service.py tests/test_schedule_run_completion_service.py tests/test_schedule_run_completion_streaming.py tests/test_schedules_router.py -q
```

Result:

```text
12 passed in 0.30s
```

Regression pack:

```text
uv run pytest tests/test_supabase_thread_repo_schema.py tests/test_supabase_schedule_repo_schema.py tests/test_schedule_service_schema_contract.py tests/test_supabase_tool_task_repo_schema.py tests/test_thread_task_tool_surface_schema.py tests/test_supabase_chat_repo_schema.py -q
```

Result:

```text
19 passed in 0.12s
```

Lint:

```text
uv run ruff check backend/web/services/message_routing.py backend/web/services/schedule_runtime_service.py backend/web/services/schedule_run_completion_service.py backend/web/services/streaming_service.py backend/web/routers/schedules.py backend/web/services/schedule_service.py tests/test_message_routing_schedule_start_only.py tests/test_schedule_runtime_service.py tests/test_schedule_run_completion_service.py tests/test_schedule_run_completion_streaming.py tests/test_schedules_router.py
```

Result:

```text
All checks passed!
```

Format:

```text
uv run ruff format --check backend/web/services/message_routing.py backend/web/services/schedule_runtime_service.py backend/web/services/schedule_run_completion_service.py backend/web/services/streaming_service.py backend/web/routers/schedules.py backend/web/services/schedule_service.py tests/test_message_routing_schedule_start_only.py tests/test_schedule_runtime_service.py tests/test_schedule_run_completion_service.py tests/test_schedule_run_completion_streaming.py tests/test_schedules_router.py
```

Result:

```text
11 files already formatted
```

## Backend API YATU

Backend proof server:

```text
BACKEND_PORT=8013 /Users/lexicalmathical/Codebase/leonai/ops/dev/run_local_supabase_backend.sh /Users/lexicalmathical/worktrees/leonai--database-refactor
```

Runtime facts:

- backend: `http://127.0.0.1:8013`
- storage: Supabase
- proof account: existing fully registered OTP account from local ops note
- proof target thread: `m_dKjuBBLbR1bw-7`
- proof target agent: `m_dKjuBBLbR1bw`
- no secrets printed

YATU flow:

1. Login through `POST /api/auth/login`.
2. Read target thread through `GET /api/threads`.
3. Create two temporary `agent.schedules` rows with service-role setup.
4. Trigger schedule 1 through authenticated `POST /api/schedules/{schedule_id}/run`.
5. Immediately trigger schedule 2 against the same target to prove active conflict.
6. Poll `agent.schedule_runs` until schedule 1 reaches terminal state.
7. Read thread detail to confirm real assistant reply.
8. Verify `public.panel_tasks` count is unchanged.
9. Cleanup temporary schedule/run rows.

Observed output:

```text
login_status=200
target_thread_id=m_dKjuBBLbR1bw-7
target_agent_user_id=m_dKjuBBLbR1bw
target_running_before=False
panel_tasks_before=2
schedule1_created=9c6377c59b5d4232b01e56be2dfef01b
schedule2_created=0e5e24fc518a4a9ab851f6cc121e61be
trigger1_status=200
schedule_run1_id=349e970a52c24bc89537719e87a9ff2e
route_runtime_run_id=b1c237af-8729-4e31-9348-9e40f29cdb9c
trigger2_status=409
trigger2_body={"detail": "target thread is already active"}
schedule1_run_count=1
schedule1_final={"completed_at_present": true, "error": null, "id": "349e970a52c24bc89537719e87a9ff2e", "routing": {"routing": "direct", "run_id": "b1c237af-8729-4e31-9348-9e40f29cdb9c", "status": "started", "thread_id": "m_dKjuBBLbR1bw-7"}, "runtime": {"run_id": "b1c237af-8729-4e31-9348-9e40f29cdb9c", "status": "succeeded", "thread_id": "m_dKjuBBLbR1bw-7"}, "status": "succeeded"}
schedule2_run_count=0
thread_entry_count=1
thread_last_reply=收到，本次定时运行已完成。
panel_tasks_after=2
panel_tasks_delta=0
cleanup_deleted_runs=1
cleanup_deleted_schedules=2
cleanup_remaining_runs=0
cleanup_remaining_schedules=0
```

Backend runtime logs confirmed real runtime/LLM path:

```text
[LeonAgent] Initialized successfully
[Memory] Context: ~89585 tokens (sys=0, msgs=89585), limit=1050000, threshold=735000, compact=no
[Memory] Final: 240 msgs (~25062 tokens) sent to LLM (original: 1191 msgs)
```

## Active Conflict Proof

The active conflict was proven through the real authenticated backend API, not only a mock:

```text
trigger2_status=409
trigger2_body={"detail": "target thread is already active"}
schedule2_run_count=0
```

This satisfies the 02J invariant: active target threads are not silently injected and do not create normal schedule run rows.

## Legacy Guard

`public.panel_tasks` did not change:

```text
panel_tasks_before=2
panel_tasks_after=2
panel_tasks_delta=0
```

## Cleanup

Temporary proof rows were removed:

```text
cleanup_deleted_runs=1
cleanup_deleted_schedules=2
cleanup_remaining_runs=0
cleanup_remaining_schedules=0
```

## Residuals

Future checkpoints:

- scheduler loop / due polling
- `create_thread_on_run`
- schedule CRUD HTTP API
- frontend schedule UX
- active-injection attribution if product later requires schedule instructions to enter already-running turns
