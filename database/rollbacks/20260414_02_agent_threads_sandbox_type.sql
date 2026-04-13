-- Roll back Database Refactor 02A sandbox_type correction.
--
-- This rollback only removes the corrective column added by
-- database/migrations/20260414_02_agent_threads_sandbox_type.sql.
-- It does not mutate public.* or staging.*.

BEGIN;

ALTER TABLE agent.threads
    DROP COLUMN IF EXISTS sandbox_type;

COMMIT;
