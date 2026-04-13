# Database Refactor Dev Replay 02: Live Agent Schema Cleanup Preflight

## Goal

Classify the current live `agent` schema state after historical/manual database-refactor work, then decide a cleanup and migration-state policy before any live DB writes.

This checkpoint is read-only. It does not merge PR #509, execute migrations, delete proof residue, route runtime repositories, or change schedules.

## Read-Only Probes

Probe file:

- `database/prechecks/20260414_02_live_agent_schema_residue_readonly.sql`

The probes were also run manually on 2026-04-14 through the private Supavisor session tunnel using the ops-recorded tenant-user connection shape. No secrets were printed or stored in this repo.

## Live Facts

Current `agent` table counts:

- `agent.threads`: 83
- `agent.thread_tasks`: 274
- `agent.schedules`: 0
- `agent.schedule_runs`: 0

Thread source/target parity:

- `staging_not_agent`: 0
- `agent_not_staging`: 2

The two target-only `agent.threads` rows are:

- `agent_yatu_17761029419594-1`
- `agent_yatu_02b_17761036443327-1`

Both rows have:

- `sandbox_type = 'local'`
- `model = 'large'`
- `status = 'active'`
- `run_status = 'idle'`
- `is_main = true`
- `branch_index = 0`
- no `cwd`
- no `last_active_at`
- no matching `staging.threads` row
- no matching agent or owner row in `staging.users`
- no matching agent or owner row in `auth.users`
- no referencing row in `agent.thread_tasks` or `staging.agent_thread_tasks`

Classification: these are standalone YATU/proof residue rows, not live product state.

Thread-task facts:

- All 274 `agent.thread_tasks` rows use `thread_id = 'test-deferred-execution'`.
- All 274 rows are `status = 'pending'`.
- All 274 rows share `subject = 'PT02_EXEC'`.
- All 274 rows share `description = 'created after discovery'`.
- All 274 rows have null `owner`, null `active_form`, empty `blocks`, empty `blocked_by`, and empty `metadata`.
- Task ids are numeric 1 through 274.
- `agent.thread_tasks` and `staging.agent_thread_tasks` are in exact parity: no source-only or target-only task rows.
- The same 274 rows also exist in `public.tool_tasks`.
- The residue is referenced only by:
  - `agent.thread_tasks.thread_id`: 274
  - `staging.agent_thread_tasks.thread_id`: 274
  - `public.tool_tasks.thread_id`: 274

Classification: this is legacy test residue copied through all task tables, not live thread-attached work.

Migration-state facts:

- `supabase_migrations.schema_migrations` has no `20260414%` rows.
- `agent.threads`, `agent.thread_tasks`, `agent.schedules`, and `agent.schedule_runs` therefore appear to have been created manually or through unrecorded scripts, not through Supabase migration state.
- `public.checkpoint_migrations` has 10 rows and only a single integer column `v`.
- `staging.checkpoint_migrations` has 0 rows and only a single integer column `v`.
- Those checkpoint tables are not an adequate durable schema-migration record for the `agent` schema replay.

Current `agent` exposure:

- Grants exist only for `service_role` on `agent.threads`, `agent.thread_tasks`, `agent.schedules`, and `agent.schedule_runs`.
- RLS is disabled for all four `agent` tables.
- No `agent` tables are in a publication.

Schema drift versus PR #509 fresh DDL:

- Current live `agent.threads.sandbox_type` is `NOT NULL`.
- Current live does not have the stricter `threads_sandbox_type_chk` check constraint from PR #509.
- Schedule tables exist even though PR #509 deliberately excludes schedule work.

## Policy Recommendation

Separate three actions. Do not combine them into one migration.

1. Merge PR #509 independently if desired.
2. Create an explicit live cleanup checkpoint for proof/test residue.
3. Create an explicit migration-state reconciliation checkpoint after cleanup policy is accepted.

## Cleanup Candidate

Candidate cleanup should be a write-only-after-approval packet, not run from this preflight:

```sql
BEGIN;

CREATE SCHEMA maintenance;

CREATE TABLE maintenance.agent_residue_cleanup_20260414 AS
SELECT 'agent.threads' AS source_table, to_jsonb(t.*) AS row_data
FROM agent.threads t
LEFT JOIN staging.threads s ON s.id = t.id
WHERE s.id IS NULL
UNION ALL
SELECT 'agent.thread_tasks' AS source_table, to_jsonb(tt.*) AS row_data
FROM agent.thread_tasks tt
WHERE tt.thread_id = 'test-deferred-execution'
UNION ALL
SELECT 'staging.agent_thread_tasks' AS source_table, to_jsonb(tt.*) AS row_data
FROM staging.agent_thread_tasks tt
WHERE tt.thread_id = 'test-deferred-execution'
UNION ALL
SELECT 'public.tool_tasks' AS source_table, to_jsonb(tt.*) AS row_data
FROM public.tool_tasks tt
WHERE tt.thread_id = 'test-deferred-execution';

DELETE FROM agent.thread_tasks
WHERE thread_id = 'test-deferred-execution';

DELETE FROM staging.agent_thread_tasks
WHERE thread_id = 'test-deferred-execution';

DELETE FROM public.tool_tasks
WHERE thread_id = 'test-deferred-execution';

DELETE FROM agent.threads t
WHERE NOT EXISTS (
    SELECT 1
    FROM staging.threads s
    WHERE s.id = t.id
);

COMMIT;
```

Expected backup rows if run against the observed state:

- 2 rows from `agent.threads`
- 274 rows from `agent.thread_tasks`
- 274 rows from `staging.agent_thread_tasks`
- 274 rows from `public.tool_tasks`
- 824 total backup rows

Expected post-cleanup counts if no concurrent writes happen:

- `agent.threads`: 81
- `agent.thread_tasks`: 0
- `staging.agent_thread_tasks`: 0
- `public.tool_tasks`: 0

This candidate intentionally uses a `maintenance` schema. That is a live-write policy choice and needs explicit approval; it is not authorized by this preflight.

## Migration-State Options

Option A: do not fake migration history.

- Keep Supabase migration state untouched.
- Treat current live as manually advanced.
- Use explicit validation docs plus cleanup proof.
- This is honest but means future automated migration tooling will not know these `agent` objects are already present.

Option B: create a reconciliation marker outside Supabase migrations.

- Add a small `maintenance.schema_reconciliation_events` table and record that `agent` DDL was manually present before dev replay.
- This avoids falsifying Supabase migration history.
- It adds one maintenance table, so it needs explicit approval.

Option C: insert synthetic rows into `supabase_migrations.schema_migrations`.

- Not recommended.
- It makes tooling believe migrations ran when they did not.
- It also cannot honestly represent the schema drift: current live has schedule tables and lacks PR #509's sandbox-type check constraint.

Recommendation: Option A for now. After cleanup, decide whether a maintenance reconciliation table is worth the extra surface area.

## Stopline

No write is authorized by this preflight.

Before any cleanup:

1. Re-run the read-only probe.
2. Confirm counts still match the expected rows.
3. Review exact cleanup SQL.
4. Decide whether backup should live in a DB `maintenance` schema or be exported outside the DB.
5. Get a separate Ledger and human authorization for the write.
