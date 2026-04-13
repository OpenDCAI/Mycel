-- Database Refactor dev replay 02 read-only live residue probes.
--
-- Scope:
-- - Classify current live agent schema state after historical/manual DDL work.
-- - Classify target-only agent.threads rows.
-- - Classify orphan thread-task residue.
-- - Inspect migration-state representation.
--
-- This file must not mutate the database.

BEGIN READ ONLY;

SELECT 'agent.threads' AS table_name, count(*) AS row_count FROM agent.threads
UNION ALL SELECT 'agent.thread_tasks', count(*) FROM agent.thread_tasks
UNION ALL SELECT 'agent.schedules', count(*) FROM agent.schedules
UNION ALL SELECT 'agent.schedule_runs', count(*) FROM agent.schedule_runs
ORDER BY table_name;

SELECT 'agent_not_staging' AS kind, count(*) AS row_count
FROM agent.threads a
LEFT JOIN staging.threads s ON s.id = a.id
WHERE s.id IS NULL
UNION ALL
SELECT 'staging_not_agent' AS kind, count(*) AS row_count
FROM staging.threads s
LEFT JOIN agent.threads a ON a.id = s.id
WHERE a.id IS NULL
ORDER BY kind;

SELECT
    a.id,
    a.agent_user_id,
    agent_user.type AS agent_type,
    agent_user.display_name AS agent_display_name,
    a.owner_user_id,
    owner_user.type AS owner_type,
    owner_user.display_name AS owner_display_name,
    a.sandbox_type,
    a.model,
    a.cwd,
    a.status,
    a.run_status,
    a.is_main,
    a.branch_index,
    a.created_at,
    a.updated_at,
    a.last_active_at
FROM agent.threads a
LEFT JOIN staging.threads s ON s.id = a.id
LEFT JOIN staging.users agent_user ON agent_user.id = a.agent_user_id
LEFT JOIN staging.users owner_user ON owner_user.id = a.owner_user_id
WHERE s.id IS NULL
ORDER BY a.created_at;

WITH target_only AS (
    SELECT a.*
    FROM agent.threads a
    LEFT JOIN staging.threads s ON s.id = a.id
    WHERE s.id IS NULL
)
SELECT
    count(*) AS target_only_threads,
    count(*) FILTER (WHERE su_agent.id IS NULL) AS missing_agent_user_in_staging_users,
    count(*) FILTER (WHERE su_owner.id IS NULL) AS missing_owner_user_in_staging_users,
    count(*) FILTER (WHERE au_agent.id IS NULL) AS missing_agent_user_in_auth_users,
    count(*) FILTER (WHERE au_owner.id IS NULL) AS missing_owner_user_in_auth_users
FROM target_only t
LEFT JOIN staging.users su_agent ON su_agent.id = t.agent_user_id
LEFT JOIN staging.users su_owner ON su_owner.id = t.owner_user_id
LEFT JOIN auth.users au_agent ON au_agent.id::text = t.agent_user_id
LEFT JOIN auth.users au_owner ON au_owner.id::text = t.owner_user_id;

WITH target_only AS (
    SELECT a.id
    FROM agent.threads a
    LEFT JOIN staging.threads s ON s.id = a.id
    WHERE s.id IS NULL
)
SELECT 'agent.thread_tasks' AS source, count(*) AS row_count
FROM agent.thread_tasks tt
JOIN target_only t ON t.id = tt.thread_id
UNION ALL
SELECT 'staging.agent_thread_tasks' AS source, count(*) AS row_count
FROM staging.agent_thread_tasks tt
JOIN target_only t ON t.id = tt.thread_id;

SELECT
    thread_id,
    status,
    owner,
    active_form,
    count(*) AS row_count,
    count(DISTINCT task_id) AS distinct_task_ids,
    count(DISTINCT subject) AS distinct_subjects
FROM agent.thread_tasks
GROUP BY thread_id, status, owner, active_form
ORDER BY row_count DESC, thread_id, status;

SELECT
    min(task_id) AS lexicographic_min_task_id,
    max(task_id) AS lexicographic_max_task_id,
    count(*) AS row_count,
    bool_and(task_id ~ '^[0-9]+$') AS all_numeric_task_ids,
    min(task_id::integer) FILTER (WHERE task_id ~ '^[0-9]+$') AS min_numeric_task_id,
    max(task_id::integer) FILTER (WHERE task_id ~ '^[0-9]+$') AS max_numeric_task_id
FROM agent.thread_tasks
WHERE thread_id = 'test-deferred-execution';

SELECT subject, description, status, count(*) AS row_count
FROM agent.thread_tasks
GROUP BY subject, description, status
ORDER BY row_count DESC, subject;

SELECT 'agent_not_staging' AS kind, count(*) AS row_count
FROM agent.thread_tasks a
LEFT JOIN staging.agent_thread_tasks s
    ON s.thread_id = a.thread_id
   AND s.task_id = a.task_id
WHERE s.task_id IS NULL
UNION ALL
SELECT 'staging_not_agent' AS kind, count(*) AS row_count
FROM staging.agent_thread_tasks s
LEFT JOIN agent.thread_tasks a
    ON a.thread_id = s.thread_id
   AND a.task_id = s.task_id
WHERE a.task_id IS NULL
ORDER BY kind;

SELECT table_schema, table_name
FROM information_schema.tables
WHERE position('migration' IN lower(table_name)) > 0
   OR position('migration' IN lower(table_schema)) > 0
ORDER BY table_schema, table_name;

SELECT version, name
FROM supabase_migrations.schema_migrations
WHERE starts_with(version, '20260414')
ORDER BY version;

SELECT table_schema, table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE (table_schema, table_name) IN (
    ('public', 'checkpoint_migrations'),
    ('staging', 'checkpoint_migrations'),
    ('supabase_migrations', 'schema_migrations')
)
ORDER BY table_schema, table_name, ordinal_position;

SELECT 'public.checkpoint_migrations' AS table_name, count(*) AS row_count
FROM public.checkpoint_migrations
UNION ALL
SELECT 'staging.checkpoint_migrations', count(*)
FROM staging.checkpoint_migrations
ORDER BY table_name;

SELECT c.relname AS table_name, con.conname, con.contype, pg_get_constraintdef(con.oid)
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'agent'
ORDER BY c.relname, con.conname;

SELECT n.nspname AS schema_name, c.relname AS table_name, c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'agent'
  AND c.relkind = 'r'
ORDER BY c.relname;

SELECT p.pubname, n.nspname AS schema_name, c.relname AS table_name
FROM pg_publication p
JOIN pg_publication_rel pr ON pr.prpubid = p.oid
JOIN pg_class c ON c.oid = pr.prrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'agent'
ORDER BY p.pubname, c.relname;

SELECT table_name, grantee, privilege_type
FROM information_schema.table_privileges
WHERE table_schema = 'agent'
  AND grantee IN ('service_role', 'authenticated', 'anon')
ORDER BY table_name, grantee, privilege_type;

COMMIT;
