-- Roll back Database Refactor 02A.
--
-- This rollback only removes the target landing tables created by
-- database/migrations/20260414_01_agent_threads_thread_tasks.sql.
-- It does not mutate public.* or staging.*.

BEGIN;

DROP TABLE IF EXISTS agent.thread_tasks;
DROP TABLE IF EXISTS agent.threads;
DROP SCHEMA IF EXISTS agent;

COMMIT;
