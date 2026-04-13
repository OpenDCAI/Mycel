# Database Refactor 02I Schedule Trigger Runtime Proof

Date: 2026-04-14

Checkpoint:

- `database-refactor-02i-schedule-trigger-runtime-preflight`

Status:

- implementation proof
- ready for Ledger closure review

## Scope Landed

02I adds the first explicit runtime path for target-thread schedules:

```text
agent.schedules -> agent.schedule_runs -> route_message_to_brain(target_thread_id)
```

Implemented surfaces:

- `backend.web.services.schedule_runtime_service.trigger_schedule`
- `backend.web.routers.schedules`
- `POST /api/schedules/{schedule_id}/run`
- `backend.web.main` router registration
- `SupabaseThreadRepo` now projects `owner_user_id` from `agent.threads`, because schedule runtime owner validation needs the same field the target schema already stores.

## Explicit Non-Scope

Not implemented in 02I:

- no cron loop
- no due schedule polling
- no `/api/panel/cron-jobs`
- no `CronService` edits
- no `panel_tasks` creation
- no frontend
- no RLS/realtime work
- no `create_thread_on_run`
- no private `_create_owned_thread` coupling
- no `succeeded` schedule run completion hook

The run lifecycle in this slice is intentionally:

```text
queued -> running
queued -> failed
```

`running` means routing was accepted by `route_message_to_brain`; it does not mean the scheduled agent work has completed.

## RED Evidence

Initial tests were written before implementation:

```text
uv run pytest tests/test_schedule_runtime_service.py tests/test_schedules_router.py -q
```

Initial RED failures:

```text
ImportError: cannot import name 'schedule_runtime_service' from 'backend.web.services'
ImportError: cannot import name 'schedules' from 'backend.web.routers'
```

Live backend YATU then exposed a real repo projection gap:

```text
trigger_status=403
trigger_body={"detail": "target thread is not owned by schedule owner"}
```

Root cause:

- live `agent.threads` contains `owner_user_id`
- `SupabaseThreadRepo.get_by_id()` did not project `owner_user_id`
- schedule runtime correctly refused to bypass owner validation

Focused RED added:

```text
uv run pytest tests/test_supabase_thread_repo_schema.py -q
```

RED failures:

```text
test_thread_repo_lists_agent_threads_by_owner_under_staging_runtime
test_thread_repo_get_by_id_exposes_owner_user_id_under_staging_runtime
```

## GREEN Evidence

Focused schedule/runtime/thread repo pack:

```text
uv run pytest tests/test_supabase_thread_repo_schema.py tests/test_schedule_runtime_service.py tests/test_schedules_router.py -q
```

Result:

```text
9 passed in 0.33s
```

Earlier focused schedule pack:

```text
uv run pytest tests/test_schedule_runtime_service.py tests/test_schedules_router.py -q
```

Result:

```text
4 passed
```

Regression pack:

```text
uv run pytest tests/test_supabase_schedule_repo_schema.py tests/test_schedule_service_schema_contract.py tests/test_supabase_tool_task_repo_schema.py tests/test_thread_task_tool_surface_schema.py tests/test_supabase_chat_repo_schema.py -q
```

Result:

```text
14 passed
```

## Backend API YATU

Backend proof server:

```text
BACKEND_PORT=8013 /Users/lexicalmathical/Codebase/leonai/ops/dev/run_local_supabase_backend.sh /Users/lexicalmathical/worktrees/leonai--database-refactor
```

Runtime facts:

- worktree: `/Users/lexicalmathical/worktrees/leonai--database-refactor`
- backend: `http://127.0.0.1:8013`
- storage strategy: Supabase
- DB schema setting: `staging`, routed to target `agent.*` repos where applicable
- proof account: existing fully registered OTP account from local ops note
- no secrets printed in proof

YATU flow:

1. Login through `POST /api/auth/login`.
2. Read owned threads through `GET /api/threads`.
3. Insert a temporary `agent.schedules` row with service-role setup.
4. Trigger through authenticated product API `POST /api/schedules/{schedule_id}/run`.
5. Read `agent.schedule_runs` through service-role verification.
6. Confirm `public.panel_tasks` count is unchanged.
7. Confirm real thread received an assistant reply.
8. Delete temporary schedule and run rows.

Observed output:

```text
login_status=200
user_id=15267c8a-a04a-40ab-b4b7-bba61cadda5b
target_thread_id=m_dKjuBBLbR1bw-7
target_agent_user_id=m_dKjuBBLbR1bw
target_running_before=False
panel_tasks_before=2
schedule_created=ffddcff5ad9946d69706cab143ab08a4
trigger_status=200
schedule_run_id=af6bbf9d812742c582e832ff8fd8a449
schedule_run_status=running
routing_status=started
routing_kind=direct
routing_run_id_present=True
persisted_run_count=1
persisted_run_status=running
persisted_run_thread_id=m_dKjuBBLbR1bw-7
persisted_run_triggered_by=manual
persisted_run_has_routing_output=True
assistant_reply_seen=True
assistant_reply_tail=收到，定时指令已到达这个线程。
panel_tasks_after=2
panel_tasks_delta=0
cleanup_deleted_runs=1
cleanup_deleted_schedules=1
cleanup_remaining_runs=0
cleanup_remaining_schedules=0
```

Follow-up runtime state check:

```text
poll 0 running False updated_at 2026-04-13T19:56:14.284777+00:00
entry_count 1
tail assistant 收到，定时指令已到达这个线程。已到达。
```

Backend runtime logs also showed real agent runtime entry:

```text
[LeonAgent] Initialized successfully
[Memory] Context: ~89353 tokens, limit=1050000, threshold=735000, compact=no
[Memory] Final: 236 msgs (~24829 tokens) sent to LLM
```

This proves the trigger reached the real runtime path. It does not prove schedule completion semantics, because 02I deliberately has no run completion hook.

## Legacy Guard

`public.panel_tasks` was checked before and after the authenticated trigger:

```text
panel_tasks_before=2
panel_tasks_after=2
panel_tasks_delta=0
```

No `CronService` or `/api/panel/cron-jobs` path was used.

## Cleanup

Temporary YATU rows were deleted:

```text
cleanup_deleted_runs=1
cleanup_deleted_schedules=1
cleanup_remaining_runs=0
cleanup_remaining_schedules=0
```

## Residuals

Remaining work belongs to later checkpoints:

- scheduler loop / due polling
- `create_thread_on_run`
- completion hook from real agent run events to `agent.schedule_runs.succeeded/failed`
- schedule CRUD HTTP API
- frontend schedule UI
