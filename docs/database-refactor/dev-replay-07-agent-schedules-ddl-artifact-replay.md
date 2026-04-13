# Database Refactor Dev Replay 07: Agent Schedules DDL Artifact Replay

## Goal

Restore the replayable fresh-environment DDL artifact for `agent.schedules` and
`agent.schedule_runs` on current `dev`, without replaying the old PR #507 runtime
work.

This checkpoint is SQL/docs only. It does not execute migrations against current
live, route schedule repositories, change APIs, change frontend behavior, add
RLS/realtime, migrate legacy cron rows, or edit migration history.

## Source Lineage

The schedule DDL comes from historical PR #507 commit:

- `8161f835` — `refactor(db): land agent schedules schema`

Only the 02G DDL artifact was replayed:

- `database/prechecks/20260414_03_agent_schedules_readonly.sql`
- `database/migrations/20260414_03_agent_schedules.sql`
- `database/rollbacks/20260414_03_agent_schedules.sql`

The later PR #507 commits are intentionally excluded from this replay:

- `5a1dde35` — schedule repo/service surface
- `84d29c2d` — schedule trigger runtime
- `9d50918b` — schedule run completion

Those are runtime/product behavior slices, not DDL artifact replay.

## Current Dev Gap

Current `dev` has the `agent.threads` / `agent.thread_tasks` replay artifact,
but no schedule DDL artifact. The existing thread/task migration explicitly says
schedules and schedule runs are not in that slice.

That means a fresh environment can replay the first agent-schema slice but cannot
replay the schedule target tables that already exist on current live.

## Live Metadata Comparison

Read-only live inspection found all four relevant tables exist and are empty:

- `agent.schedules`: 0 rows
- `agent.schedule_runs`: 0 rows
- `public.cron_jobs`: 0 rows
- `staging.cron_jobs`: 0 rows

Observed live `agent.schedules` columns:

- `id`
- `owner_user_id`
- `agent_user_id`
- `target_thread_id`
- `create_thread_on_run`
- `cron_expression`
- `enabled`
- `instruction_template`
- `timezone`
- `last_run_at`
- `next_run_at`
- `created_at`
- `updated_at`

Observed live `agent.schedule_runs` columns:

- `id`
- `schedule_id`
- `owner_user_id`
- `agent_user_id`
- `thread_id`
- `status`
- `triggered_by`
- `scheduled_for`
- `started_at`
- `completed_at`
- `input_json`
- `output_json`
- `error`
- `created_at`

The replayed DDL matches this live shape:

- schedule targeting is explicit through `target_thread_id` or
  `create_thread_on_run`
- schedule execution belongs to both `owner_user_id` and `agent_user_id`
- run status values are `queued`, `running`, `succeeded`, `failed`,
  `cancelled`
- trigger sources are `scheduler` and `manual`
- access is service-role only
- RLS is not enabled
- realtime publication is not added

## Migration Stance

The migration is for fresh environments where:

- schema `agent` already exists
- `agent.threads` already exists
- `agent.schedules` does not exist
- `agent.schedule_runs` does not exist
- `public.cron_jobs` and `staging.cron_jobs` are empty

It fails loudly if either legacy cron table contains rows. A cron data migration
would require a separate ruling, because `cron_jobs` is a legacy name and not the
target schedule ontology.

Current live already has the target schedule tables and has no rows in either
target or legacy schedule tables. Therefore this migration must not be executed
on current live under this checkpoint.

## Stopline

No write is authorized by this checkpoint.

Before any schedule runtime work:

1. Land the DDL artifact independently.
2. Decide whether to replay the old 02H schedule repo/service surface or redesign
   it against current `dev`.
3. Keep manual trigger runtime, run completion, due polling, frontend schedule UX,
   RLS/realtime, and legacy cron deletion as separate checkpoints.
