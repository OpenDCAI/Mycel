-- Database Refactor 02A corrective read-only prechecks.
-- Run before executing database/migrations/20260414_02_agent_threads_sandbox_type.sql.
-- This file must not mutate the database.

-- 1. The target table from 02A must already exist.
SELECT count(*) AS agent_threads_exists
FROM information_schema.tables
WHERE table_schema = 'agent'
  AND table_name = 'threads';

-- 2. The correction must not have already been applied.
SELECT count(*) AS agent_threads_sandbox_type_exists
FROM information_schema.columns
WHERE table_schema = 'agent'
  AND table_name = 'threads'
  AND column_name = 'sandbox_type';

-- 3. The source column must exist and be text-compatible.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'staging'
  AND table_name = 'threads'
  AND column_name = 'sandbox_type';

-- 4. Source values must be present for every migrated target row.
SELECT count(*) AS missing_source_sandbox_type
FROM agent.threads a
LEFT JOIN staging.threads s ON s.id = a.id
WHERE s.id IS NULL
   OR s.sandbox_type IS NULL
   OR btrim(s.sandbox_type) = '';

-- 5. Source and target row sets must still match before the correction.
SELECT count(*) AS agent_threads_without_staging_source
FROM agent.threads a
LEFT JOIN staging.threads s ON s.id = a.id
WHERE s.id IS NULL;

SELECT count(*) AS staging_threads_without_agent_target
FROM staging.threads s
LEFT JOIN agent.threads a ON a.id = s.id
WHERE a.id IS NULL;

-- 6. Show the distinct source values being copied into agent.threads.
SELECT sandbox_type, count(*) AS count
FROM staging.threads
GROUP BY sandbox_type
ORDER BY count DESC, sandbox_type;
