# Database Refactor 02 Preflight: Thread Tasks And Schedules

Date: 2026-04-14

Status: design/preflight only. No DDL, no DB writes, no runtime route change.

Ledger boundary: this packet exists to request a checkpoint ruling before any Database Refactor 02 implementation.

## Recommendation

Split the originally suggested `thread_tasks/schedules` slice.

The first implementation slice should be:

1. Create the `agent` schema foundation needed for runtime ownership.
2. Land `agent.threads` from the current `staging.threads`.
3. Land `agent.thread_tasks` from the current `staging.agent_thread_tasks`.
4. Route the Supabase thread/task repos to explicit domain schemas.

Do not migrate schedules in the same slice.

Reason: `thread_tasks` depends on thread ownership and can be closed with a narrow backend API YATU. `schedules` currently comes from legacy `cron_jobs`, whose runtime behavior creates `panel_tasks`. The design target says panel tasks should be removed, and `schedule_runs` introduces new execution semantics. Combining those with `thread_tasks` would turn one database migration into a product behavior redesign.

## Source Inputs

- Upstream design comment: `https://github.com/nmhjklnm/mycel-db-design/issues/1#issuecomment-4237192274`
- Design repo: `/Users/lexicalmathical/Codebase/mycel-db-design` at `9422bd8`
- Current Mycel PR: `https://github.com/OpenDCAI/Mycel/pull/507`
- Current contract matrix: `docs/database-refactor/target-contract-matrix.md`
- Live DB queried through the existing staging backend `LEON_POSTGRES_URL`; secrets were not printed.

## Design Conflict To Resolve

The upstream design repo still says `agent.tool_tasks`, but the accepted Mycel ruling is `agent.thread_tasks`.

More importantly, upstream `agent.tool_tasks` DDL models long-running tool execution progress:

- `id`
- `run_id`
- `tool_name`
- `input_json`
- `output_json`
- `progress_json`
- `expires_at`

Current Mycel `tool_tasks` / `agent_thread_tasks` model is different. It is the thread-scoped task-list state used by `core.tools.task`:

- `thread_id`
- `task_id`
- `subject`
- `description`
- `status`
- `active_form`
- `owner`
- `blocks`
- `blocked_by`
- `metadata`

Therefore Database Refactor 02 must not copy the upstream `agent.tool_tasks` DDL as-is. For Mycel, the target table should be `agent.thread_tasks` with the current thread task contract. If Mycel later needs long-running tool execution progress, that should be a separate table and checkpoint, not this migration.

## Live DB Facts

### Thread tasks

`public.tool_tasks`:

- rows: 274
- primary key: `(thread_id, task_id)`
- statuses: `pending = 274`
- distinct `thread_id`: 1
- orphaned against `public.threads`: 274 rows

`staging.agent_thread_tasks`:

- rows: 274
- primary key: `(thread_id, task_id)`
- statuses: `pending = 274`
- distinct `thread_id`: 1
- orphaned against `staging.threads`: 274 rows

The two current task tables have the same logical columns. `staging.agent_thread_tasks` is the better source because this refactor is moving from the staging runtime surface toward domain schemas.

### Threads

`staging.threads`:

- rows: 81
- columns: `id`, `agent_user_id`, `sandbox_type`, `model`, `cwd`, `status`, `created_at`, `updated_at`, `last_active_at`, `is_main`, `branch_index`
- missing target `owner_user_id`, but it can be derived by joining `staging.users.id = staging.threads.agent_user_id`

`public.threads`:

- rows: 62
- legacy `member_id`, `user_id`, `observation_provider`, `agent`

Use `staging.threads` as the source for `agent.threads`.

### Schedules

`public.cron_jobs`:

- rows: 0
- legacy bigint timestamps
- has `owner_user_id`

`staging.cron_jobs`:

- rows: 0
- legacy bigint timestamps
- has FK to `staging.users(id)`

There is no schedule data to migrate right now. The work is product/API semantics, not data preservation.

### Panel tasks

`public.panel_tasks`:

- rows: 2
- statuses: `pending = 1`, `completed = 1`
- sources: `agent = 1`, `manual = 1`

`staging.panel_tasks`:

- absent

Panel tasks are not part of the target schema. They should not be migrated into `agent.thread_tasks` or `agent.schedules`.

## Code Surfaces

### Thread tasks

- `core/tools/task/service.py`
- `core/tools/task/types.py`
- `storage/providers/supabase/tool_task_repo.py`
- `storage/providers/sqlite/tool_task_repo.py`
- `backend/web/core/storage_factory.py::make_tool_task_repo`
- Tests:
  - add Supabase schema route tests for the renamed table
  - keep existing SQLite task service tests passing

### Threads

- `storage/providers/supabase/thread_repo.py`
- `tests/test_supabase_thread_repo_schema.py`
- Backend API surfaces already smoke-tested in PR #507:
  - `POST /api/auth/login`
  - `GET /api/members`
  - `GET /api/threads`

### Schedules / legacy cron

- `storage/providers/supabase/cron_job_repo.py`
- `storage/providers/sqlite/cron_job_repo.py`
- `backend/web/services/cron_job_service.py`
- `backend/web/services/cron_service.py`
- `backend/web/routers/panel.py` `/cron-jobs`
- `frontend/app/src/pages/TasksPage.tsx`
- `frontend/app/src/components/cron-editor.tsx`
- `frontend/app/src/components/task-modal.tsx`
- `frontend/app/src/store/app-store.ts`

This is too broad to mix with the first domain table migration.

## Target Contract For Database Refactor 02A

### `agent.threads`

This table is required because `agent.thread_tasks` ownership, RLS, and future realtime visibility need a domain-thread source of truth.

Minimum target columns:

```sql
CREATE SCHEMA IF NOT EXISTS agent;

CREATE TABLE agent.threads (
    id                   TEXT        PRIMARY KEY,
    agent_user_id        TEXT        NOT NULL,
    owner_user_id        TEXT        NOT NULL,
    current_workspace_id TEXT,
    model                TEXT,
    cwd                  TEXT,
    status               TEXT        NOT NULL DEFAULT 'active',
    run_status           TEXT        NOT NULL DEFAULT 'idle',
    is_main              BOOLEAN     NOT NULL DEFAULT false,
    branch_index         INTEGER     NOT NULL DEFAULT 0,
    last_active_at       TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT threads_status_chk
        CHECK (status IN ('active', 'archived')),
    CONSTRAINT threads_run_status_chk
        CHECK (run_status IN ('idle', 'running', 'paused', 'error')),
    CONSTRAINT threads_agent_branch_uq UNIQUE (agent_user_id, branch_index)
);

CREATE INDEX idx_threads_owner_active
    ON agent.threads(owner_user_id, last_active_at DESC)
    WHERE status = 'active';

CREATE INDEX idx_threads_agent_active
    ON agent.threads(agent_user_id)
    WHERE status = 'active';
```

Migration source:

```sql
INSERT INTO agent.threads (
    id,
    agent_user_id,
    owner_user_id,
    model,
    cwd,
    status,
    run_status,
    is_main,
    branch_index,
    last_active_at,
    created_at,
    updated_at
)
SELECT
    t.id,
    t.agent_user_id,
    u.owner_user_id,
    t.model,
    t.cwd,
    t.status,
    'idle',
    (t.is_main <> 0),
    t.branch_index,
    CASE WHEN t.last_active_at IS NULL THEN NULL ELSE to_timestamp(t.last_active_at) END,
    to_timestamp(t.created_at),
    CASE WHEN t.updated_at IS NULL THEN to_timestamp(t.created_at) ELSE to_timestamp(t.updated_at) END
FROM staging.threads t
JOIN staging.users u ON u.id = t.agent_user_id
WHERE u.owner_user_id IS NOT NULL;
```

Pre-migration check:

```sql
SELECT count(*) FROM staging.threads t
LEFT JOIN staging.users u ON u.id = t.agent_user_id
WHERE u.id IS NULL OR u.owner_user_id IS NULL;
```

This must be zero or explicitly waived before implementation.

### `agent.thread_tasks`

Use the current Mycel thread task contract, not upstream `agent.tool_tasks` progress DDL.

```sql
CREATE TABLE agent.thread_tasks (
    thread_id    TEXT  NOT NULL,
    task_id      TEXT  NOT NULL,
    subject      TEXT  NOT NULL,
    description  TEXT  NOT NULL,
    status       TEXT  NOT NULL DEFAULT 'pending',
    active_form  TEXT,
    owner        TEXT,
    blocks       JSONB NOT NULL DEFAULT '[]',
    blocked_by   JSONB NOT NULL DEFAULT '[]',
    metadata     JSONB NOT NULL DEFAULT '{}',

    PRIMARY KEY (thread_id, task_id),
    CONSTRAINT thread_tasks_status_chk
        CHECK (status IN ('pending', 'in_progress', 'completed'))
);

CREATE INDEX idx_thread_tasks_thread
    ON agent.thread_tasks(thread_id);
```

Migration source:

```sql
INSERT INTO agent.thread_tasks (
    thread_id,
    task_id,
    subject,
    description,
    status,
    active_form,
    owner,
    blocks,
    blocked_by,
    metadata
)
SELECT
    thread_id,
    task_id,
    subject,
    description,
    status,
    active_form,
    owner,
    blocks,
    blocked_by,
    metadata
FROM staging.agent_thread_tasks;
```

Pre-migration issue: current 274 rows are orphaned against `staging.threads`. That means the insert above will preserve rows, but if `agent.thread_tasks` later adds a hard FK to `agent.threads`, these rows will fail. For this slice, do not add a hard FK. Ownership/RLS can still use `EXISTS(agent.threads...)`; orphan rows will simply be invisible to authenticated users until cleaned.

## Supabase Client Contract

PR #507 made `LEON_DB_SCHEMA` explicit for the current `public/staging` runtime. The target multi-schema design cannot keep relying on one global PostgREST default schema.

Supabase-py supports:

```python
client.schema("agent").table("thread_tasks")
```

Database Refactor 02A should add a tiny domain table helper rather than broad compatibility branches. Expected shape:

```python
def table_in_schema(client: Any, schema: str, table: str) -> Any:
    return client.schema(schema).table(table)
```

Then `SupabaseToolTaskRepo` should become either:

- `SupabaseThreadTaskRepo`, or
- a backward-compatible class name that targets `agent.thread_tasks` while the Python symbol rename happens in a follow-up.

The table name must become `thread_tasks`. Do not keep a permanent `tool_tasks` fallback.

## Migration Artifact Shape

Create a versioned SQL artifact under a repo-owned path, for example:

```text
database/migrations/20260414_01_agent_threads_thread_tasks.sql
```

The artifact should be one transaction:

1. `CREATE SCHEMA IF NOT EXISTS agent`
2. create `agent.threads`
3. create `agent.thread_tasks`
4. copy from `staging.threads`
5. copy from `staging.agent_thread_tasks`
6. create indexes
7. enable RLS only if policies can be proved against the migrated `agent.threads`
8. add realtime publication for `agent.threads` and `agent.thread_tasks`
9. run parity assertions at the end

Suggested parity assertions:

```sql
SELECT
    (SELECT count(*) FROM staging.threads t JOIN staging.users u ON u.id = t.agent_user_id WHERE u.owner_user_id IS NOT NULL) AS source_threads,
    (SELECT count(*) FROM agent.threads) AS target_threads;

SELECT
    (SELECT count(*) FROM staging.agent_thread_tasks) AS source_tasks,
    (SELECT count(*) FROM agent.thread_tasks) AS target_tasks;
```

## Rollback Plan

Because this is a landing migration, rollback should be simple:

```sql
DROP TABLE IF EXISTS agent.thread_tasks;
DROP TABLE IF EXISTS agent.threads;
DROP SCHEMA IF EXISTS agent;
```

Do not delete or mutate `staging.*` or `public.*` in this slice. Old tables remain intact until a later purge checkpoint.

## Backend/API YATU Closure Path

Run against real Supabase with `LEON_STORAGE_STRATEGY=supabase`.

Minimum backend API YATU:

1. Login with a real test user.
2. `GET /api/threads` returns 200 and still lists the same visible threads as before the route switch.
3. Exercise the Task tool through a real thread path or a high-level backend API that writes through `core.tools.task.service`.
4. Verify `agent.thread_tasks` row count changes when a thread task is created.
5. Verify `GET /api/threads` still returns 200 after task creation.

Source/test auxiliary evidence:

- RED/GREEN repo tests for `SupabaseThreadTaskRepo` table route.
- RED/GREEN tests proving no permanent `tool_tasks` table route remains in Supabase mode.
- Storage runtime wiring tests.
- `ruff check` and `ruff format --check`.

## Schedules Follow-Up Packet

Schedules should be a separate checkpoint after 02A.

Reasoning:

- `cron_jobs` has zero rows, so there is no urgent data migration.
- Current `CronService.trigger_job()` creates `panel_tasks`.
- Target `agent.schedules.task_template` should steer or create agent threads, not create legacy panel board rows.
- `agent.schedule_runs` changes runtime observability and needs new service behavior.
- The frontend Tasks/Cron UI is tied to legacy panel semantics.

The follow-up checkpoint should decide one of these product directions before DDL:

1. Remove legacy Tasks/Cron UI and replace it with agent schedule UI.
2. Keep a compatibility UI label but route it to agent schedules.
3. Park schedules until a real product loop exists.

Do not silently migrate `panel_tasks` into schedules or thread tasks.

## Stopline

Stop and return to Ledger if any of these happen:

- `thread_tasks` implementation starts adding permanent `tool_tasks` fallback.
- The migration needs to mutate or delete `public.*` / `staging.*`.
- The code starts mixing legacy `panel_tasks` into `agent.thread_tasks`.
- The work requires frontend Tasks/Cron redesign.
- Supabase domain schema routing becomes broad repo-specific branching instead of a small explicit helper.
