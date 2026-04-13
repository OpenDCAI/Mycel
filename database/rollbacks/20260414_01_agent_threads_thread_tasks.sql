-- Roll back Database Refactor dev replay 01.
--
-- Scope:
-- - Remove only the target landing objects created by
--   database/migrations/20260414_01_agent_threads_thread_tasks.sql.
--
-- Non-goals:
-- - No mutation of public.* or staging.*.
-- - No schedule rollback. If later agent.* tables exist, roll them back first;
--   DROP SCHEMA agent should fail loudly instead of hiding extra objects.

BEGIN;

DROP TABLE agent.thread_tasks;
DROP TABLE agent.threads;
DROP SCHEMA agent;

COMMIT;
