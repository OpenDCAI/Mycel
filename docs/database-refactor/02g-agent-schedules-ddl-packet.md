# Database Refactor 02G Agent Schedules DDL Packet

Date: 2026-04-14

Checkpoint:

- `database-refactor-02g-agent-schedules-ddl-precheck-and-migration`

Status:

- packet accepted by Ledger
- live DDL executed after Ledger authorization
- post-execution proof: `docs/database-refactor/02g-agent-schedules-ddl-execution-proof.md`

## Stopline

02G may only touch the target schedule tables:

- `agent.schedules`
- `agent.schedule_runs`

02G must not:

- mutate or delete `public.*`
- mutate or delete `staging.*`
- migrate `panel_tasks`
- migrate `cron_jobs`
- change runtime repository routing
- change `/cron-jobs` API behavior
- change frontend behavior
- add RLS/realtime policies

## Artifacts

Read-only precheck:

- `database/prechecks/20260414_03_agent_schedules_readonly.sql`

Migration:

- `database/migrations/20260414_03_agent_schedules.sql`

Rollback:

- `database/rollbacks/20260414_03_agent_schedules.sql`

## Read-Only Live Precheck Output

Executed against the live Supabase Postgres target through the private local tunnel. Secrets were not printed.

```text
agent_schema_exists:
  1
agent_threads_exists:
  1
agent_schedules_exists:
  0
agent_schedule_runs_exists:
  0
agent_threads_key_columns:
  id | text | NO
  agent_user_id | text | NO
  owner_user_id | text | NO
public_cron_jobs:
  0
staging_cron_jobs:
  0
public_panel_tasks_not_migrated:
  2
service_role_has_agent_usage:
  True
```

Interpretation:

- `agent` schema foundation from 02A exists.
- `agent.threads` exists and has the required identity columns.
- `agent.schedules` and `agent.schedule_runs` do not already exist.
- live `public.cron_jobs` and `staging.cron_jobs` are empty, so 02G does not need a cron data migration.
- `public.panel_tasks` has rows, but panel tasks are explicitly rejected as schedule source data and are not touched.
- `service_role` already has `agent` schema usage.

## DDL Shape

`agent.schedules` stores the schedule contract:

- owner user
- agent user
- optional target thread
- explicit `create_thread_on_run`
- cron expression
- enabled flag
- instruction template
- timezone
- last/next run timestamps

The key validity constraint is:

```text
target_thread_id IS NOT NULL OR create_thread_on_run
```

This fails loudly if a schedule has no execution target.

`agent.schedule_runs` stores execution history:

- schedule id
- owner user
- agent user
- optional thread id
- status
- trigger source
- scheduled/started/completed timestamps
- input/output JSON
- error text

Initial run states:

```text
queued
running
succeeded
failed
cancelled
```

Initial trigger sources:

```text
scheduler
manual
```

## Grants, PostgREST, And RLS Stance

Grants:

- grant `SELECT, INSERT, UPDATE, DELETE` on both new tables to `service_role`
- rely on 02A's existing `GRANT USAGE ON SCHEMA agent TO service_role`

PostgREST:

- `agent` is already expected to be exposed from the 02A runbook.
- If service-role REST visibility fails because the PostgREST schema cache is stale, reload the schema cache as an operational step, not a schema fallback.

RLS/realtime:

- no RLS policy in 02G
- no realtime publication in 02G
- direct frontend access and authenticated-user policy design require a separate checkpoint

## Service-Role REST Proof Plan

After Ledger authorizes and the migration executes:

1. Query `agent.schedules` and `agent.schedule_runs` through the service-role Supabase REST client.
2. Insert one temporary schedule row with `create_thread_on_run = true`.
3. Insert one temporary schedule run row referencing the temporary schedule id.
4. Select both rows back through service-role REST.
5. Delete the temporary run row, then delete the temporary schedule row.
6. Confirm cleanup returns zero rows for the temporary ids.

This proof only validates DDL visibility and service-role access. It does not claim scheduler runtime behavior.

## Rollback Scope

Rollback drops only:

- `agent.schedule_runs`
- `agent.schedules`

It does not mutate `public.*` or `staging.*`.

## Execution Gate

Ledger accepted this packet and authorized executing only `database/migrations/20260414_03_agent_schedules.sql`.

No further runtime route, frontend, RLS, realtime, cron compatibility, or panel-task work is authorized by this packet.
