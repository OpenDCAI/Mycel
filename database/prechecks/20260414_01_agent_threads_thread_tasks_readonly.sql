-- Database Refactor 02A read-only prechecks.
-- Run before executing database/migrations/20260414_01_agent_threads_thread_tasks.sql.
-- This file must not mutate the database.

-- 1. Every staging thread must resolve to an owner_user_id through staging.users.
SELECT count(*) AS owner_derivation_missing
FROM staging.threads t
LEFT JOIN staging.users u ON u.id = t.agent_user_id
WHERE u.id IS NULL OR u.owner_user_id IS NULL;

-- 2. agent.threads target uniqueness must be safe.
SELECT agent_user_id, branch_index, count(*) AS duplicate_count
FROM staging.threads
GROUP BY agent_user_id, branch_index
HAVING count(*) > 1
ORDER BY duplicate_count DESC, agent_user_id, branch_index;

-- 3. staging thread statuses must fit the target check constraint.
SELECT status, count(*) AS count
FROM staging.threads
WHERE status NOT IN ('active', 'archived')
GROUP BY status
ORDER BY status;

-- 4. Unix epoch timestamps must be safe for to_timestamp().
SELECT count(*) AS negative_thread_timestamps
FROM staging.threads
WHERE created_at < 0 OR updated_at < 0 OR last_active_at < 0;

-- 5. Prove the source column types expected by the migration.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'staging'
  AND table_name = 'threads'
  AND column_name IN ('is_main', 'created_at', 'updated_at', 'last_active_at')
ORDER BY column_name;

-- 6. thread_tasks statuses must fit the target check constraint.
SELECT status, count(*) AS count
FROM staging.agent_thread_tasks
WHERE status NOT IN ('pending', 'in_progress', 'completed')
GROUP BY status
ORDER BY status;

-- 7. thread_tasks required fields and JSONB fields must not contain nulls.
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

-- 8. Expected source row counts.
SELECT count(*) AS source_threads_for_agent_threads
FROM staging.threads t
JOIN staging.users u ON u.id = t.agent_user_id
WHERE u.owner_user_id IS NOT NULL;

SELECT count(*) AS source_thread_tasks
FROM staging.agent_thread_tasks;

-- 9. Known orphan source tasks. These are preserved without a hard FK in 02A.
SELECT count(*) AS orphan_thread_tasks_against_staging_threads
FROM staging.agent_thread_tasks tt
LEFT JOIN staging.threads t ON t.id = tt.thread_id
WHERE t.id IS NULL;

-- 10. This migration is first-run-only: the target schema must not exist yet.
SELECT count(*) AS agent_schema_exists
FROM information_schema.schemata
WHERE schema_name = 'agent';
