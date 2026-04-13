# Database Refactor 02G Agent Schedules DDL Execution Proof

Date: 2026-04-14

Checkpoint:

- `database-refactor-02g-agent-schedules-ddl-precheck-and-migration`

Status:

- live DDL executed
- service-role REST proof passed
- no runtime behavior change

## Authorized Scope

Ledger authorized executing only:

- `database/migrations/20260414_03_agent_schedules.sql`

The authorized migration scope was:

- create `agent.schedules`
- create `agent.schedule_runs`
- grant service-role table access
- run service-role REST insert/select/delete proof

Not authorized and not done:

- no `public.*` mutation
- no `staging.*` mutation
- no `cron_jobs` migration
- no `panel_tasks` migration
- no runtime route change
- no `/cron-jobs` API behavior change
- no frontend change
- no RLS/realtime change
- no schedule trigger implementation

## Pre-Execution Check

Immediately before migration execution:

```text
precheck:
  agent_schema_exists: 1
  agent_threads_exists: 1
  agent_schedules_exists: 0
  agent_schedule_runs_exists: 0
  public_cron_jobs: 0
  staging_cron_jobs: 0
  public_panel_tasks_not_migrated: 2
```

## Migration Execution

Executed path:

```text
database/migrations/20260414_03_agent_schedules.sql
```

Migration output:

```text
migration_executed: database/migrations/20260414_03_agent_schedules.sql
```

## Metadata Proof

Tables:

```text
agent | schedule_runs
agent | schedules
```

Columns:

```text
schedule_runs | id | text | NO |
schedule_runs | schedule_id | text | NO |
schedule_runs | owner_user_id | text | NO |
schedule_runs | agent_user_id | text | NO |
schedule_runs | thread_id | text | YES |
schedule_runs | status | text | NO | 'queued'::text
schedule_runs | triggered_by | text | NO |
schedule_runs | scheduled_for | timestamp with time zone | YES |
schedule_runs | started_at | timestamp with time zone | YES |
schedule_runs | completed_at | timestamp with time zone | YES |
schedule_runs | input_json | jsonb | NO | '{}'::jsonb
schedule_runs | output_json | jsonb | NO | '{}'::jsonb
schedule_runs | error | text | YES |
schedule_runs | created_at | timestamp with time zone | NO | now()
schedules | id | text | NO |
schedules | owner_user_id | text | NO |
schedules | agent_user_id | text | NO |
schedules | target_thread_id | text | YES |
schedules | create_thread_on_run | boolean | NO | false
schedules | cron_expression | text | NO |
schedules | enabled | boolean | NO | true
schedules | instruction_template | text | NO |
schedules | timezone | text | NO | 'UTC'::text
schedules | last_run_at | timestamp with time zone | YES |
schedules | next_run_at | timestamp with time zone | YES |
schedules | created_at | timestamp with time zone | NO | now()
schedules | updated_at | timestamp with time zone | NO | now()
```

Constraints:

```text
agent.schedule_runs | schedule_runs_pkey | p
agent.schedule_runs | schedule_runs_status_chk | c
agent.schedule_runs | schedule_runs_triggered_by_chk | c
agent.schedules | schedules_cron_expression_chk | c
agent.schedules | schedules_instruction_template_chk | c
agent.schedules | schedules_pkey | p
agent.schedules | schedules_target_chk | c
agent.schedules | schedules_timezone_chk | c
```

Indexes:

```text
schedule_runs | idx_schedule_runs_owner_created
schedule_runs | idx_schedule_runs_schedule_created
schedule_runs | idx_schedule_runs_status_scheduled
schedule_runs | schedule_runs_pkey
schedules | idx_schedules_agent
schedules | idx_schedules_owner_enabled_next_run
schedules | idx_schedules_target_thread
schedules | schedules_pkey
```

Service-role grants:

```text
schedule_runs | DELETE
schedule_runs | INSERT
schedule_runs | SELECT
schedule_runs | UPDATE
schedules | DELETE
schedules | INSERT
schedules | SELECT
schedules | UPDATE
```

Legacy table counts after migration:

```text
public_cron_jobs | staging_cron_jobs | public_panel_tasks
0 | 0 | 2
```

This confirms the migration did not mutate `cron_jobs` or `panel_tasks`.

## Service-Role REST Proof

Proof shape:

- inserted one temporary row into `agent.schedules`
- inserted one temporary row into `agent.schedule_runs`
- selected both rows back through service-role REST
- deleted the temporary run row
- deleted the temporary schedule row
- confirmed cleanup returned zero rows for both temporary ids

Output:

```text
inserted_schedule_rows: 1
inserted_run_rows: 1
selected_schedule_rows: 1
selected_run_rows: 1
deleted_run_rows: 1
deleted_schedule_rows: 1
remaining_run_rows: 0
remaining_schedule_rows: 0
```

PostgREST schema cache reload was not required.

## Claim Boundary

02G proves only:

- live DDL exists for `agent.schedules` and `agent.schedule_runs`
- service-role can access both tables through Supabase REST
- temporary proof data can be cleaned up
- legacy `cron_jobs` and `panel_tasks` counts were preserved

02G does not prove:

- scheduler runtime behavior
- agent thread execution from schedules
- `/cron-jobs` compatibility behavior
- frontend schedule UX
- authenticated-user/RLS policy behavior
