# Database Refactor 02A Execution Proof

Date: 2026-04-14

Scope executed:

- `database/migrations/20260414_01_agent_threads_thread_tasks.sql`
- PostgREST exposed schemas update: add `agent`
- `supabase-rest` restart only
- service-role REST visibility proof

Not executed:

- no runtime repo route to `agent.*`
- no RLS
- no realtime
- no schedules / cron_jobs / panel_tasks migration
- no mutation or deletion of `public.*` or `staging.*`

## Precheck Before Execution

Read-only precheck was run immediately before migration.

Results:

- statement count: 11
- owner derivation missing: 0
- duplicate `(agent_user_id, branch_index)` pairs: 0 rows
- unsupported thread statuses: 0 rows
- negative thread timestamps: 0
- source column types:
  - `created_at`: `double precision`, not null
  - `is_main`: `integer`, not null
  - `last_active_at`: `double precision`, nullable
  - `updated_at`: `double precision`, nullable
- bad thread task statuses: 0 rows
- thread task required nulls: 0
- source threads for `agent.threads`: 81
- source thread tasks: 274
- orphan thread tasks against `staging.threads`: 274
- `agent` schema exists before migration: 0

## Migration Result

The migration executed successfully.

Post-execution row/parity checks:

- `agent` schema exists: 1
- `agent.threads`: 81
- `agent.thread_tasks`: 274
- `staging.threads`: 81
- `staging.agent_thread_tasks`: 274
- `public.tool_tasks`: 274

Privilege checks:

- `service_role` has `USAGE` on schema `agent`: true
- `service_role` can `SELECT` `agent.threads`: true
- `service_role` can `SELECT` `agent.thread_tasks`: true
- `anon` has `USAGE` on schema `agent`: false
- `authenticated` has `USAGE` on schema `agent`: false

## PostgREST Exposure

Remote self-hosted Supabase config was updated from:

```text
PGRST_DB_SCHEMAS=public,storage,graphql_public,staging
```

to:

```text
PGRST_DB_SCHEMAS=public,storage,graphql_public,staging,agent
```

Only `supabase-rest` was recreated/restarted through docker compose.

Container proof after restart:

```text
PGRST_DB_SCHEMAS=public,storage,graphql_public,staging,agent
supabase-rest Up
```

## Service-Role REST Proof

Using the app Supabase service-role environment:

```python
client = create_supabase_client()
threads = client.schema("agent").table("threads").select("id").limit(1).execute()
tasks = client.schema("agent").table("thread_tasks").select("thread_id,task_id").limit(1).execute()
```

Result:

- first attempt succeeded
- `agent_threads_data_is_list`: true, length 1
- `agent_thread_tasks_data_is_list`: true, length 1

## Existing Staging Surface Smoke

Against the already-running backend on port 8010:

- `POST /api/auth/login`: 200, token present
- `GET /api/threads`: 200

`GET /api/members` returned 404 on this backend version, which appears to be a route/version mismatch rather than a DB failure. It did not return a 5xx. Do not use that endpoint as closure evidence for this execution slice.

## Current Stopline

Do not route runtime repos to `agent.*` until Ledger reviews this proof.

Do not add RLS/realtime/anon/authenticated grants in this checkpoint.

## Sandbox Type Correction

Ledger authorized a narrow corrective migration after the initial execution proof found a runtime contract mismatch:

- `agent.threads` had landed without `sandbox_type`
- current `SupabaseThreadRepo` reads `sandbox_type`
- current `/api/threads` derives the response `sandbox` field from `sandbox_type`
- current runtime pool keys use `thread_id:sandbox_type`

Local `psql` was not installed, so the exact SQL files were executed through the project Python environment with `psycopg`. Secrets were not printed.

Corrective artifacts:

- precheck: `database/prechecks/20260414_02_agent_threads_sandbox_type_readonly.sql`
- migration: `database/migrations/20260414_02_agent_threads_sandbox_type.sql`
- rollback: `database/rollbacks/20260414_02_agent_threads_sandbox_type.sql`

Read-only precheck immediately before execution:

- statement count: 7
- `agent_threads_exists`: 1
- `agent_threads_sandbox_type_exists`: 0
- source `staging.threads.sandbox_type`: `text`, not null
- `missing_source_sandbox_type`: 0
- `agent_threads_without_staging_source`: 0
- `staging_threads_without_agent_target`: 0
- source distribution:
  - `local`: 56
  - `daytona_selfhost`: 25

Migration result:

- `database/migrations/20260414_02_agent_threads_sandbox_type.sql` executed successfully
- no default value was added
- no application fallback was added
- no runtime routing was performed
- no `public.*` or `staging.*` mutation was performed

Post-execution DB proof:

- `agent.threads.sandbox_type`: `text`, not null, no default
- blank/null `agent.threads.sandbox_type` rows: 0
- `agent.threads`: 81
- `staging.threads`: 81
- `agent.thread_tasks`: 274
- `staging.agent_thread_tasks`: 274
- `public.tool_tasks`: 274
- target distribution:
  - `local`: 56
  - `daytona_selfhost`: 25

Service-role REST proof:

```python
client = create_supabase_client()
result = client.schema("agent").table("threads").select("id,sandbox_type").limit(3).execute()
```

Result:

- `agent_threads_data_is_list`: true
- `agent_threads_len`: 3
- returned fields: `id`, `sandbox_type`
- sample returned sandbox types: `local`

Note: the first REST proof attempt hit local SOCKS proxy bleed because inherited `ALL_PROXY` made `httpx` require `socksio`. The proof was rerun with `ALL_PROXY/all_proxy` unset, matching the repo playbook.

## Runtime Routing Service-Role Boundary

Fresh backend proof on port `18010` found a real permission stopline:

- `POST /api/auth/login`: 200
- `GET /api/threads`: 500 before the runtime wiring fix
- backend traceback: `SupabaseThreadRepo.list_by_owner_user_id` selected `agent.threads` with a user-authenticated PostgREST identity
- PostgREST returned SQLSTATE `42501`, `permission denied for schema agent`

Ledger ruling:

- do not grant `anon` or `authenticated` access to `agent.*` in 02A
- do not add RLS policies in 02A just to make direct authenticated PostgREST work
- keep `LEON_DB_SCHEMA=staging` globally for auth/account/member/entity surfaces
- keep migrated `agent.threads` and `agent.thread_tasks` behind the backend service-role repository boundary

Code correction:

- `backend.web.core.lifespan` now creates two Supabase clients in Supabase mode:
  - storage client for repos and `StorageContainer`
  - auth client for `AuthService`
- reason: Supabase auth calls mutate the client's auth headers; storage repos must keep service-role identity
- no grants, RLS, default schema fallback, or global `LEON_DB_SCHEMA=agent` path were added

Regression test:

```text
uv run pytest tests/test_lifespan_supabase_wiring.py tests/test_supabase_tool_task_repo_schema.py tests/test_supabase_thread_repo_schema.py tests/test_supabase_factory.py tests/test_threads_router_agent_schema_contract.py tests/test_supabase_member_repo_schema.py -q
15 passed
```

Lint/format:

```text
uv run ruff check backend/web/core/lifespan.py tests/test_lifespan_supabase_wiring.py
All checks passed!

uv run ruff format --check backend/web/core/lifespan.py tests/test_lifespan_supabase_wiring.py
2 files already formatted
```

Fresh backend API YATU after the fix:

- backend env: `LEON_STORAGE_STRATEGY=supabase`, `LEON_DB_SCHEMA=staging`
- `POST /api/auth/login`: 200
- `GET /api/threads`: 200
- response for a temporary fresh user: `{"threads": []}`
- temporary auth/user rows were cleaned up

Task tool storage proof through `agent.thread_tasks`:

- `TaskCreate`: created task id `1`
- `TaskList`: total `1`
- `TaskGet`: status `pending`
- `TaskUpdate`: status `completed`
- direct service-role read from `agent.thread_tasks`: 1 matching row
- proof row was deleted after the check

High-level ToolRunner proof through the registered task tools:

- `ToolRunner.wrap_tool_call(TaskCreate)`: created task id `1`
- `ToolRunner.wrap_tool_call(TaskList)`: total `1`
- `ToolRunner.wrap_tool_call(TaskGet)`: status `pending`
- `ToolRunner.wrap_tool_call(TaskUpdate)`: status `completed`
- upstream fallback handler calls: 0
- direct service-role read from `agent.thread_tasks`: 1 matching row
- proof row was deleted after the check

Direct PostgREST access remains denied:

- anon REST request to `agent.threads`: HTTP 401, code `42501`
- authenticated REST request to `agent.threads`: HTTP 403, code `42501`

## Follow-Up Non-02A Blocker

`POST /api/threads` still failed during an expanded proof attempt, but the failure is outside the `agent.*` repo-routing fix:

- `POST /api/threads`: 500
- traceback: `SupabaseEntityRepo.get_by_id` tried to read `staging.entities`
- PostgREST returned `PGRST205`, table `staging.entities` not found in schema cache

This should be tracked as a separate entity/thread-create checkpoint. It should not be patched inside 02A by adding fallback routing or inventing `staging.entities` without a target-contract decision.

Resolution:

- handled by `database-refactor-02b-supabase-actor-read-model-adapter`
- proof: `docs/database-refactor/02b-actor-read-model-proof.md`
