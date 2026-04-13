# Database Refactor 02B Actor Read-Model Proof

Date: 2026-04-14

Checkpoint:

- `database-refactor-02b-supabase-actor-read-model-adapter`

Scope executed:

- Remove Supabase runtime dependency on a nonexistent `entities` table.
- Derive actor/entity read model from canonical sources:
  - human and agent rows from `staging.users`
  - agent main thread linkage from `agent.threads`
- Fix the expanded thread-create path that writes `thread_launch_prefs` under staging:
  - application contract still uses `member_id`
  - staging database column is `agent_user_id`

Not executed:

- no DDL
- no `public.entities`, `staging.entities`, or `agent.entities`
- no fallback routing
- no frontend redesign
- no identity/chat schema migration

## Root Cause

The first expanded backend API proof after 02A failed at `POST /api/threads`:

- `SupabaseEntityRepo.get_by_id` queried `staging.entities`
- live staging has no `entities` table
- PostgREST returned `PGRST205`

After replacing `SupabaseEntityRepo` with a read-model adapter, the next real runtime blocker surfaced:

- `SupabaseThreadLaunchPrefRepo.save_successful` wrote `member_id`
- live `staging.thread_launch_prefs` has `agent_user_id`, not `member_id`
- PostgREST returned `PGRST204`

The correction is explicit schema mapping, not fallback:

- `public.thread_launch_prefs`: `member_id`
- `staging.thread_launch_prefs`: `agent_user_id`

## Code Correction

`SupabaseEntityRepo` is now a no-table read-model adapter:

- `get_by_id(id)` loads the member row from `staging.users`
- human actors become `EntityRow(type="human")`
- agent actors become `EntityRow(type="agent")`
- agent `thread_id` is derived from `SupabaseThreadRepo.get_main_thread(member.id)`
- create/update/delete are no-ops because there is no Supabase entity table to mutate in this checkpoint

`SupabaseThreadLaunchPrefRepo` now routes its agent identity column through `LEON_DB_SCHEMA`:

- application input/output remains `member_id`
- staging reads/writes `agent_user_id`
- unknown runtime schemas fail loudly

## Test Evidence

RED was observed before implementation:

- `tests/test_supabase_entity_repo_schema.py`: 4 failures because the old repo queried `entities`
- `tests/test_supabase_thread_launch_pref_repo_schema.py`: 3 failures because the old repo queried/wrote `member_id` under staging and did not reject unknown schemas

GREEN after implementation:

```text
uv run pytest tests/test_supabase_thread_launch_pref_repo_schema.py tests/test_supabase_entity_repo_schema.py tests/test_lifespan_supabase_wiring.py tests/test_supabase_tool_task_repo_schema.py tests/test_supabase_thread_repo_schema.py tests/test_supabase_factory.py tests/test_threads_router_agent_schema_contract.py tests/test_supabase_member_repo_schema.py -q
22 passed
```

Lint/format:

```text
uv run ruff check storage/providers/supabase/thread_launch_pref_repo.py tests/test_supabase_thread_launch_pref_repo_schema.py storage/providers/supabase/entity_repo.py tests/test_supabase_entity_repo_schema.py
All checks passed!

uv run ruff format --check storage/providers/supabase/thread_launch_pref_repo.py tests/test_supabase_thread_launch_pref_repo_schema.py storage/providers/supabase/entity_repo.py tests/test_supabase_entity_repo_schema.py
4 files already formatted
```

## Backend API YATU

Fresh backend was launched on validation port `18010` with:

- `LEON_STORAGE_STRATEGY=supabase`
- `LEON_DB_SCHEMA=staging`
- public Supabase REST/auth target
- private Postgres/Supavisor runtime via the existing ops startup script

Known non-blocking startup notes:

- local provider was available
- Daytona/AgentBay SDK imports still failed because optional SDK packages are not installed in this venv
- those provider-load warnings did not affect the local-provider thread-create proof

Real product-path proof used a temporary Supabase auth user plus temporary `staging.users` human/agent rows. Secrets and password were not recorded.

Results:

- `POST /api/auth/login`: 200
- `GET /api/threads` before create: 200, count 0
- `POST /api/threads`: 200
- created thread id: `agent_yatu_wy14scan-1`
- `GET /api/threads` after create: 200
- created thread present in response: true
- `GET /api/entities`: 200
- temporary agent present with created thread id: true
- `staging.thread_launch_prefs` row for `(owner_user_id, agent_user_id)`: 1

Cleanup completed:

- deleted temporary `agent.threads` row
- deleted temporary `staging.thread_launch_prefs` row
- deleted temporary `staging.users` agent row
- deleted temporary `staging.users` human row
- deleted temporary Supabase auth user

## Stopline

02B does not authorize adding an `entities` table back into Supabase.

If later product design needs a durable actor projection table, that must be a new checkpoint with a target-schema decision. For this checkpoint, actor discovery is a read model derived from canonical user/thread state.
