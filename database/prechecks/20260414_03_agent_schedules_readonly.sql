-- Database Refactor 02G read-only prechecks.
-- Run before executing database/migrations/20260414_03_agent_schedules.sql.
-- This file must not mutate the database.

-- 1. The agent schema and agent.threads foundation from 02A must already exist.
SELECT count(*) AS agent_schema_exists
FROM information_schema.schemata
WHERE schema_name = 'agent';

SELECT count(*) AS agent_threads_exists
FROM information_schema.tables
WHERE table_schema = 'agent'
  AND table_name = 'threads';

-- 2. The schedule target tables must not already exist.
SELECT count(*) AS agent_schedules_exists
FROM information_schema.tables
WHERE table_schema = 'agent'
  AND table_name = 'schedules';

SELECT count(*) AS agent_schedule_runs_exists
FROM information_schema.tables
WHERE table_schema = 'agent'
  AND table_name = 'schedule_runs';

-- 3. Required agent.threads identity columns must exist.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'agent'
  AND table_name = 'threads'
  AND column_name IN ('id', 'agent_user_id', 'owner_user_id')
ORDER BY ordinal_position;

-- 4. Existing legacy schedule rows must be empty because 02G does not migrate cron_jobs.
SELECT count(*) AS public_cron_jobs
FROM public.cron_jobs;

SELECT count(*) AS staging_cron_jobs
FROM staging.cron_jobs;

-- 5. Panel tasks are explicitly rejected as schedule source data; show their count only.
SELECT count(*) AS public_panel_tasks_not_migrated
FROM public.panel_tasks;

-- 6. Service role must already have agent schema usage from 02A.
SELECT has_schema_privilege('service_role', 'agent', 'USAGE') AS service_role_has_agent_usage;
