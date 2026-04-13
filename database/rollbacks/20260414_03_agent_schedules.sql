-- Roll back Database Refactor 02G.
--
-- This rollback only removes the target schedule tables created by
-- database/migrations/20260414_03_agent_schedules.sql.
-- It does not mutate public.* or staging.*.

BEGIN;

DROP TABLE IF EXISTS agent.schedule_runs;
DROP TABLE IF EXISTS agent.schedules;

COMMIT;
