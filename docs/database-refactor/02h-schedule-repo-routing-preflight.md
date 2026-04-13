# Database Refactor 02H Schedule Repo Routing Preflight

Date: 2026-04-14

Checkpoint:

- `database-refactor-02h-schedule-repo-routing-preflight`

Status:

- preflight accepted by Ledger
- implementation complete
- closure proof: `docs/database-refactor/02h-schedule-repo-routing-proof.md`

## Goal

Create the first runtime-facing repository/service surface for the 02G tables:

- `agent.schedules`
- `agent.schedule_runs`

This must be a clean schedule ontology surface, not a hidden rewrite of legacy `cron_jobs`.

## Current Facts

Existing legacy runtime is cron/panel-task-shaped:

- `storage/providers/supabase/cron_job_repo.py`
  - stores in `cron_jobs`
  - fields: `name`, `description`, `cron_expression`, `task_template`, `enabled`, `last_run_at`, `next_run_at`, `created_at`
- `backend/web/services/cron_job_service.py`
  - thin CRUD wrapper over `make_cron_job_repo`
- `backend/web/services/cron_service.py`
  - reads cron jobs
  - creates legacy panel tasks through `task_service.create_task`
  - writes `cron_job_id` into panel task data
- `backend/web/routers/panel.py`
  - exposes `/api/panel/cron-jobs`
  - create/update/list/delete/run endpoints are still named cron jobs
- `frontend/app/src/store/types.ts`
  - still has `CronJob`
- `frontend/app/src/pages/TasksPage.tsx`
  - still drives cron job UI

The new 02G table requires fields that legacy `/cron-jobs` does not provide:

- `owner_user_id`
- `agent_user_id`
- `target_thread_id` or `create_thread_on_run`
- `instruction_template`

Therefore, directly rerouting legacy `/cron-jobs` create/update calls into `agent.schedules` would require invented defaults or request-context guesswork. That would violate the no-fallback/no-patch stance.

## Recommended 02H Contract

02H should introduce an explicit schedule repository/service surface and prove it routes to `agent.*`.

Do this:

- create `storage/providers/supabase/schedule_repo.py`
- expose `SupabaseScheduleRepo`
- add `make_schedule_repo()` in `backend/web/core/storage_factory.py`
- create `backend/web/services/schedule_service.py`
- add focused tests for repo/service routing
- run a service-role CRUD proof against live Supabase

Do not do this in 02H:

- do not change `/api/panel/cron-jobs`
- do not change `CronService`
- do not create panel tasks
- do not add schedule trigger execution
- do not change frontend
- do not add RLS/realtime
- do not add compatibility fallback from old cron fields to schedule fields

## Exact Repository Surface

`SupabaseScheduleRepo` should provide schedule CRUD:

```python
class SupabaseScheduleRepo:
    def list_by_owner(self, owner_user_id: str) -> list[dict]: ...
    def get(self, schedule_id: str) -> dict | None: ...
    def create(
        self,
        *,
        owner_user_id: str,
        agent_user_id: str,
        cron_expression: str,
        instruction_template: str,
        target_thread_id: str | None = None,
        create_thread_on_run: bool = False,
        enabled: bool = True,
        timezone: str = "UTC",
        next_run_at: str | None = None,
    ) -> dict: ...
    def update(self, schedule_id: str, **fields: Any) -> dict | None: ...
    def delete(self, schedule_id: str) -> bool: ...
```

It should provide minimal run-history methods:

```python
class SupabaseScheduleRepo:
    def create_run(
        self,
        *,
        schedule_id: str,
        owner_user_id: str,
        agent_user_id: str,
        triggered_by: str,
        thread_id: str | None = None,
        scheduled_for: str | None = None,
        input_json: dict | None = None,
    ) -> dict: ...
    def list_runs(self, schedule_id: str) -> list[dict]: ...
    def update_run(self, run_id: str, **fields: Any) -> dict | None: ...
    def delete_run(self, run_id: str) -> bool: ...
```

Reason to keep one repo class in 02H:

- both tables are part of the same schedule storage aggregate
- no runtime trigger lifecycle exists yet
- splitting schedule and run repos now adds ceremony without behavior

## Service Surface

`backend/web/services/schedule_service.py` should be a thin validation/wrapper layer:

- `list_schedules(owner_user_id: str)`
- `get_schedule(schedule_id: str)`
- `create_schedule(...)`
- `update_schedule(schedule_id: str, **fields)`
- `delete_schedule(schedule_id: str)`
- `create_schedule_run(...)`
- `list_schedule_runs(schedule_id: str)`
- `update_schedule_run(run_id: str, **fields)`
- `delete_schedule_run(run_id: str)`

Validation should be minimal and aligned with table constraints:

- `owner_user_id` must be non-empty
- `agent_user_id` must be non-empty
- `cron_expression` must be non-empty
- `instruction_template` must be non-empty
- at least one of `target_thread_id` or `create_thread_on_run` must be true
- `triggered_by` must be `scheduler` or `manual`
- `status`, if updated, must be one of `queued`, `running`, `succeeded`, `failed`, `cancelled`

Do not validate cron syntax in 02H unless an existing helper is directly reused without broadening scope. The DB only requires non-empty cron expression; trigger semantics belong to a later runtime checkpoint.

## Schema Mapping

For Supabase runtime:

- when `LEON_DB_SCHEMA=staging`, schedule storage uses `client.schema("agent").table("schedules")`
- when `LEON_DB_SCHEMA=staging`, schedule run storage uses `client.schema("agent").table("schedule_runs")`
- `public` must not route to `agent.*` by accident
- unknown runtime schemas must fail loudly

Recommended stance:

```text
staging -> agent.schedules / agent.schedule_runs
public  -> unsupported for new schedule repo
other   -> unsupported
```

Reason:

- `public.cron_jobs` is legacy
- 02G created the new schedule ontology under `agent`
- a new schedule repo should not preserve public legacy behavior

## Rejected Approaches

### Rejected: Rewrite SupabaseCronJobRepo To Use agent.schedules

Problem:

- `/cron-jobs` create does not pass `owner_user_id`
- `/cron-jobs` create does not pass `agent_user_id`
- legacy `task_template` is not the same as `instruction_template`
- legacy run endpoint returns a panel task, not a schedule run

This would require invented defaults and hidden translation. That is exactly the fallback-shaped compatibility layer 02F warned against.

### Rejected: Route CronService Trigger To Schedule Runs In 02H

Problem:

- schedule run lifecycle has not been designed at product/API level
- agent thread execution from a schedule has not been proven
- panel task creation must not be silently preserved

This belongs to a later checkpoint.

### Rejected: Add Frontend Schedule UX In 02H

Problem:

- current UI is task/cron/panel shaped
- schedule creation needs agent/thread targeting
- frontend changes would widen scope beyond repo routing

This belongs after backend schedule API semantics are clear.

## RED/GREEN Plan

### RED 1: Supabase schedule repo routes staging to agent tables

Create `tests/test_supabase_schedule_repo_schema.py`.

Test shape:

```python
def test_schedule_repo_uses_agent_tables_under_staging_runtime(monkeypatch):
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    tables = {}
    repo = SupabaseScheduleRepo(FakeSupabaseClient(tables))

    created = repo.create(
        owner_user_id="owner_1",
        agent_user_id="agent_1",
        cron_expression="*/15 * * * *",
        instruction_template="Summarize project state",
        create_thread_on_run=True,
    )

    assert created["owner_user_id"] == "owner_1"
    assert tables["agent.schedules"][0]["agent_user_id"] == "agent_1"
    assert "cron_jobs" not in tables
```

Expected RED:

- import fails because `SupabaseScheduleRepo` does not exist

### RED 2: Unknown/public schema fails loudly

Test shape:

```python
def test_schedule_repo_rejects_public_runtime_schema(monkeypatch):
    monkeypatch.setenv("LEON_DB_SCHEMA", "public")

    with pytest.raises(RuntimeError):
        SupabaseScheduleRepo(FakeSupabaseClient()).list_by_owner("owner_1")
```

Expected RED:

- import fails before implementation

### RED 3: Schedule service refuses invalid target

Create `tests/test_schedule_service_schema_contract.py`.

Test shape:

```python
def test_schedule_service_requires_target_thread_or_create_thread(monkeypatch):
    monkeypatch.setattr(schedule_service, "make_schedule_repo", lambda: FakeScheduleRepo())

    with pytest.raises(ValueError, match="target"):
        schedule_service.create_schedule(
            owner_user_id="owner_1",
            agent_user_id="agent_1",
            cron_expression="*/15 * * * *",
            instruction_template="work",
        )
```

Expected RED:

- import fails because `schedule_service` does not exist

### GREEN

Implement only enough to pass these tests:

- `storage/providers/supabase/schedule_repo.py`
- `backend/web/core/storage_factory.py::make_schedule_repo`
- `backend/web/services/schedule_service.py`
- exports in `storage/providers/supabase/__init__.py`

No router, frontend, scheduler, or panel task changes.

## Verification Plan

Local source/test proof:

```bash
uv run pytest tests/test_supabase_schedule_repo_schema.py tests/test_schedule_service_schema_contract.py -q
uv run pytest tests/test_supabase_tool_task_repo_schema.py tests/test_thread_task_tool_surface_schema.py tests/test_supabase_chat_repo_schema.py -q
uv run ruff check storage/providers/supabase/schedule_repo.py backend/web/services/schedule_service.py backend/web/core/storage_factory.py tests/test_supabase_schedule_repo_schema.py tests/test_schedule_service_schema_contract.py
uv run ruff format --check storage/providers/supabase/schedule_repo.py backend/web/services/schedule_service.py backend/web/core/storage_factory.py tests/test_supabase_schedule_repo_schema.py tests/test_schedule_service_schema_contract.py
```

Live service-role CRUD proof:

- set `LEON_STORAGE_STRATEGY=supabase`
- set `LEON_DB_SCHEMA=staging`
- use service-role Supabase runtime
- call `schedule_service.create_schedule(...)`
- call `schedule_service.get_schedule(...)`
- call `schedule_service.list_schedules(owner_user_id)`
- call `schedule_service.update_schedule(...)`
- call `schedule_service.create_schedule_run(...)`
- call `schedule_service.list_schedule_runs(schedule_id)`
- call `schedule_service.update_schedule_run(...)`
- delete temporary rows
- prove cleanup returns zero rows

This proof is mechanism-level storage/service proof, not YATU product closure. Product-level YATU waits until there is an authenticated backend API or frontend surface.

## Stopline

Stop immediately and return to Ledger if implementation appears to require any of these:

- adding request fields to `/api/panel/cron-jobs`
- changing `/api/panel/cron-jobs`
- changing `CronService`
- creating panel tasks
- implementing agent thread execution from schedule runs
- adding frontend schedule UI
- granting authenticated/anon direct table access
- adding RLS/realtime
- mapping `public.cron_jobs` or `staging.cron_jobs` into `agent.schedules`

The acceptable 02H closure is narrow:

```text
New explicit schedule repo/service surface routes to agent.schedules and agent.schedule_runs under staging Supabase runtime, with no legacy cron fallback and no trigger behavior.
```
