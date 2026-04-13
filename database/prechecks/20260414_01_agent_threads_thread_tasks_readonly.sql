-- Database Refactor dev replay 01 read-only precheck.
--
-- Scope:
-- - Inspect the current staging source shape for agent.threads and agent.thread_tasks.
-- - Inspect whether target agent tables already exist.
-- - Do not mutate data, schemas, grants, or publications.
--
-- Run before considering database/migrations/20260414_01_agent_threads_thread_tasks.sql.

BEGIN READ ONLY;

-- Source table presence.
SELECT table_schema, table_name
FROM information_schema.tables
WHERE (table_schema, table_name) IN (
    ('staging', 'threads'),
    ('staging', 'agent_thread_tasks'),
    ('staging', 'users'),
    ('agent', 'threads'),
    ('agent', 'thread_tasks')
)
ORDER BY table_schema, table_name;

-- Source column contracts expected by the migration.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'staging'
  AND table_name = 'threads'
ORDER BY ordinal_position;

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'staging'
  AND table_name = 'agent_thread_tasks'
ORDER BY ordinal_position;

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'staging'
  AND table_name = 'users'
ORDER BY ordinal_position;

-- Every staging thread must resolve to an owner_user_id through staging.users.
SELECT count(*) AS owner_derivation_missing
FROM staging.threads t
LEFT JOIN staging.users u ON u.id = t.agent_user_id
WHERE u.id IS NULL
   OR u.owner_user_id IS NULL;

-- agent.threads target uniqueness must be safe.
SELECT agent_user_id, branch_index, count(*) AS duplicate_count
FROM staging.threads
GROUP BY agent_user_id, branch_index
HAVING count(*) > 1
ORDER BY duplicate_count DESC, agent_user_id, branch_index;

-- staging thread statuses must fit the target check constraint.
SELECT status, count(*) AS count
FROM staging.threads
WHERE status NOT IN ('active', 'archived')
GROUP BY status
ORDER BY status;

-- Unix epoch timestamps must be safe for to_timestamp().
SELECT count(*) AS negative_thread_timestamps
FROM staging.threads
WHERE created_at < 0
   OR updated_at < 0
   OR last_active_at < 0;

-- sandbox_type is required in the current dev runtime contract.
SELECT count(*) AS blank_sandbox_type
FROM staging.threads
WHERE sandbox_type IS NULL
   OR btrim(sandbox_type) = '';

-- thread_tasks statuses must fit the target check constraint.
SELECT status, count(*) AS count
FROM staging.agent_thread_tasks
WHERE status NOT IN ('pending', 'in_progress', 'completed')
GROUP BY status
ORDER BY status;

-- thread_tasks required fields and JSONB fields must not contain nulls.
SELECT count(*) AS thread_task_required_nulls
FROM staging.agent_thread_tasks
WHERE thread_id IS NULL
   OR task_id IS NULL
   OR subject IS NULL
   OR description IS NULL
   OR status IS NULL
   OR blocks IS NULL
   OR blocked_by IS NULL
   OR metadata IS NULL;

-- Source row counts.
SELECT count(*) AS source_threads_for_agent_threads
FROM staging.threads t
JOIN staging.users u ON u.id = t.agent_user_id
WHERE u.owner_user_id IS NOT NULL;

SELECT count(*) AS source_thread_tasks
FROM staging.agent_thread_tasks;

-- Known source-task integrity gap. This slice preserves tasks without a hard FK.
SELECT count(*) AS orphan_thread_tasks_against_staging_threads
FROM staging.agent_thread_tasks tt
LEFT JOIN staging.threads t ON t.id = tt.thread_id
WHERE t.id IS NULL;

-- This migration is first-run-only. Existing target objects mean current live
-- has already been advanced and needs validation/cleanup, not this migration.
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'agent';

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'agent'
ORDER BY table_name;

COMMIT;
