# Database Refactor 02H Schedule Repo Routing Proof

Date: 2026-04-14

Checkpoint:

- `database-refactor-02h-schedule-repo-routing-preflight`

Status:

- implementation complete
- mechanism-level repo/service proof passed
- no product YATU claimed

## Scope Implemented

Created an explicit schedule repo/service surface for:

- `agent.schedules`
- `agent.schedule_runs`

Files changed:

- `storage/providers/supabase/schedule_repo.py`
- `backend/web/services/schedule_service.py`
- `backend/web/core/storage_factory.py`
- `storage/providers/supabase/__init__.py`
- `tests/test_supabase_schedule_repo_schema.py`
- `tests/test_schedule_service_schema_contract.py`
- `docs/database-refactor/02h-schedule-repo-routing-preflight.md`

## Stopline Held

Not changed:

- no `/api/panel/cron-jobs` route changes
- no `CronService` changes
- no panel task creation
- no schedule trigger runtime
- no frontend work
- no RLS/realtime
- no public/staging cron_jobs mapping
- no cron_jobs or panel_tasks migration
- no authenticated/anon table grants

## Implementation Shape

`SupabaseScheduleRepo` is one storage aggregate over both schedule tables.

Under `LEON_DB_SCHEMA=staging`:

- schedules route to `client.schema("agent").table("schedules")`
- schedule runs route to `client.schema("agent").table("schedule_runs")`

`public` and unknown schemas fail loudly through the explicit schema router. This avoids silently preserving legacy `public.cron_jobs`.

`schedule_service` is a thin validation wrapper:

- validates non-empty owner/agent/cron/instruction/timezone fields
- requires `target_thread_id` or `create_thread_on_run`
- validates run trigger source
- validates run status updates
- delegates storage to `make_schedule_repo`

The implementation includes `delete_schedule_run` because the live CRUD proof needs to clean temporary run rows. This is cleanup CRUD, not trigger/runtime behavior.

## RED Evidence

Initial focused test run before implementation:

```text
ERROR tests/test_supabase_schedule_repo_schema.py
ModuleNotFoundError: No module named 'storage.providers.supabase.schedule_repo'

ERROR tests/test_schedule_service_schema_contract.py
ImportError: cannot import name 'schedule_service' from 'backend.web.services'
```

This was the expected RED state: the new repo/service surface did not exist.

## GREEN Evidence

Focused tests:

```text
uv run pytest tests/test_supabase_schedule_repo_schema.py tests/test_schedule_service_schema_contract.py -q
......                                                                   [100%]
6 passed in 0.02s
```

Wider schema regression pack:

```text
uv run pytest tests/test_supabase_schedule_repo_schema.py tests/test_schedule_service_schema_contract.py tests/test_supabase_tool_task_repo_schema.py tests/test_thread_task_tool_surface_schema.py tests/test_supabase_chat_repo_schema.py tests/test_supabase_thread_repo_schema.py tests/test_supabase_entity_repo_schema.py tests/test_supabase_member_repo_schema.py tests/test_supabase_thread_launch_pref_repo_schema.py tests/test_threads_router_agent_schema_contract.py -q
.............................                                            [100%]
29 passed in 0.37s
```

Ruff:

```text
uv run ruff check storage/providers/supabase/schedule_repo.py backend/web/services/schedule_service.py backend/web/core/storage_factory.py storage/providers/supabase/__init__.py tests/test_supabase_schedule_repo_schema.py tests/test_schedule_service_schema_contract.py
All checks passed!
```

Format:

```text
uv run ruff format --check storage/providers/supabase/schedule_repo.py backend/web/services/schedule_service.py backend/web/core/storage_factory.py storage/providers/supabase/__init__.py tests/test_supabase_schedule_repo_schema.py tests/test_schedule_service_schema_contract.py
6 files already formatted
```

## Live Service-Role CRUD Proof

Proof used `schedule_service`, not direct table-only calls.

Runtime shape:

- `LEON_STORAGE_STRATEGY=supabase`
- `LEON_DB_SCHEMA=staging`
- service-role Supabase runtime
- command run with `ALL_PROXY` / `all_proxy` unset to avoid known SOCKS proxy bleed

First attempt without unsetting proxy failed at supabase-py `.schema()` with the known SOCKS proxy import error. This was an environment issue, not schedule logic. The successful proof used the repo-local runtime rule: unset proxy env for Supabase service proof.

Successful proof output:

```text
created_schedule_id_prefix: 7af6e1fc
fetched_schedule_rows: 1
listed_owner_schedule_rows: 1
updated_schedule_enabled: False
created_run_id_prefix: b0ea9f92
listed_run_rows: 1
updated_run_status: running
updated_run_thread_id_prefix: thread_0
deleted_run: True
deleted_schedule: True
remaining_run_rows: 0
remaining_schedule_rows: 0
remaining_owner_schedule_rows: 0
```

This proves:

- `schedule_service.create_schedule` writes `agent.schedules`
- `schedule_service.get_schedule` reads the row
- `schedule_service.list_schedules` filters by owner
- `schedule_service.update_schedule` updates the row
- `schedule_service.create_schedule_run` writes `agent.schedule_runs`
- `schedule_service.list_schedule_runs` reads run history
- `schedule_service.update_schedule_run` updates run status/thread metadata
- `schedule_service.delete_schedule_run` cleans up the run
- `schedule_service.delete_schedule` cleans up the schedule
- cleanup left zero temporary rows

## Claim Boundary

02H proves mechanism-level routing only:

- explicit schedule repo/service exists
- staging Supabase runtime routes to `agent.schedules` and `agent.schedule_runs`
- public/unknown schedule repo schemas fail loudly
- service-role CRUD works through `schedule_service`

02H does not prove product-level behavior:

- no authenticated schedule API
- no frontend schedule UX
- no scheduler loop
- no agent thread execution from schedules
- no `/cron-jobs` compatibility behavior
- no RLS/authenticated-user policy
