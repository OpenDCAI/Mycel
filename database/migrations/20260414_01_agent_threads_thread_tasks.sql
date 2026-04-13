-- Database Refactor 02A: land agent.threads and agent.thread_tasks.
--
-- Scope:
-- - Create agent schema.
-- - Copy staging.threads into agent.threads.
-- - Copy staging.agent_thread_tasks into agent.thread_tasks.
--
-- Non-goals:
-- - No mutation or deletion of public.* / staging.*.
-- - No schedules / cron_jobs / panel_tasks migration.
-- - No hard FK from agent.thread_tasks to agent.threads because current source
--   agent_thread_tasks rows are known orphaned against staging.threads.
-- - No RLS/realtime in this migration. Add them only after policy/publication
--   behavior is proved in a separate checkpoint.
-- - First-run-only: fail if the agent schema already exists. This avoids
--   hiding partial landing state behind IF NOT EXISTS / ON CONFLICT behavior.

BEGIN;

DO $$
DECLARE
    v_agent_schema_count integer;
    v_missing_owner_count integer;
    v_duplicate_branch_count integer;
    v_bad_status_count integer;
    v_negative_timestamp_count integer;
    v_bad_task_status_count integer;
    v_task_required_null_count integer;
BEGIN
    SELECT count(*)
    INTO v_agent_schema_count
    FROM information_schema.schemata
    WHERE schema_name = 'agent';

    IF v_agent_schema_count <> 0 THEN
        RAISE EXCEPTION 'Cannot migrate 02A: schema agent already exists';
    END IF;

    SELECT count(*)
    INTO v_missing_owner_count
    FROM staging.threads t
    LEFT JOIN staging.users u ON u.id = t.agent_user_id
    WHERE u.id IS NULL OR u.owner_user_id IS NULL;

    IF v_missing_owner_count <> 0 THEN
        RAISE EXCEPTION 'Cannot migrate agent.threads: % staging.threads rows lack owner_user_id derivation', v_missing_owner_count;
    END IF;

    SELECT count(*)
    INTO v_duplicate_branch_count
    FROM (
        SELECT agent_user_id, branch_index
        FROM staging.threads
        GROUP BY agent_user_id, branch_index
        HAVING count(*) > 1
    ) duplicates;

    IF v_duplicate_branch_count <> 0 THEN
        RAISE EXCEPTION 'Cannot migrate agent.threads: % duplicate (agent_user_id, branch_index) pairs', v_duplicate_branch_count;
    END IF;

    SELECT count(*)
    INTO v_bad_status_count
    FROM staging.threads
    WHERE status NOT IN ('active', 'archived');

    IF v_bad_status_count <> 0 THEN
        RAISE EXCEPTION 'Cannot migrate agent.threads: % rows have unsupported status', v_bad_status_count;
    END IF;

    SELECT count(*)
    INTO v_negative_timestamp_count
    FROM staging.threads
    WHERE created_at < 0 OR updated_at < 0 OR last_active_at < 0;

    IF v_negative_timestamp_count <> 0 THEN
        RAISE EXCEPTION 'Cannot migrate agent.threads: % rows have negative timestamps', v_negative_timestamp_count;
    END IF;

    SELECT count(*)
    INTO v_bad_task_status_count
    FROM staging.agent_thread_tasks
    WHERE status NOT IN ('pending', 'in_progress', 'completed');

    IF v_bad_task_status_count <> 0 THEN
        RAISE EXCEPTION 'Cannot migrate agent.thread_tasks: % rows have unsupported status', v_bad_task_status_count;
    END IF;

    SELECT count(*)
    INTO v_task_required_null_count
    FROM staging.agent_thread_tasks
    WHERE thread_id IS NULL
       OR task_id IS NULL
       OR subject IS NULL
       OR description IS NULL
       OR status IS NULL
       OR blocks IS NULL
       OR blocked_by IS NULL
       OR metadata IS NULL;

    IF v_task_required_null_count <> 0 THEN
        RAISE EXCEPTION 'Cannot migrate agent.thread_tasks: % rows have required nulls', v_task_required_null_count;
    END IF;
END $$;

CREATE SCHEMA agent;

CREATE TABLE agent.threads (
    id                   TEXT        PRIMARY KEY,
    agent_user_id        TEXT        NOT NULL,
    owner_user_id        TEXT        NOT NULL,
    current_workspace_id TEXT,
    model                TEXT,
    cwd                  TEXT,
    status               TEXT        NOT NULL DEFAULT 'active',
    run_status           TEXT        NOT NULL DEFAULT 'idle',
    is_main              BOOLEAN     NOT NULL DEFAULT false,
    branch_index         INTEGER     NOT NULL DEFAULT 0,
    last_active_at       TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT threads_status_chk
        CHECK (status IN ('active', 'archived')),
    CONSTRAINT threads_run_status_chk
        CHECK (run_status IN ('idle', 'running', 'paused', 'error')),
    CONSTRAINT threads_agent_branch_uq UNIQUE (agent_user_id, branch_index)
);

CREATE INDEX idx_threads_owner_active
    ON agent.threads(owner_user_id, last_active_at DESC)
    WHERE status = 'active';

CREATE INDEX idx_threads_agent_active
    ON agent.threads(agent_user_id)
    WHERE status = 'active';

CREATE TABLE agent.thread_tasks (
    thread_id    TEXT  NOT NULL,
    task_id      TEXT  NOT NULL,
    subject      TEXT  NOT NULL,
    description  TEXT  NOT NULL,
    status       TEXT  NOT NULL DEFAULT 'pending',
    active_form  TEXT,
    owner        TEXT,
    blocks       JSONB NOT NULL DEFAULT '[]',
    blocked_by   JSONB NOT NULL DEFAULT '[]',
    metadata     JSONB NOT NULL DEFAULT '{}',

    PRIMARY KEY (thread_id, task_id),
    CONSTRAINT thread_tasks_status_chk
        CHECK (status IN ('pending', 'in_progress', 'completed'))
);

CREATE INDEX idx_thread_tasks_thread
    ON agent.thread_tasks(thread_id);

GRANT USAGE ON SCHEMA agent TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON agent.threads TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON agent.thread_tasks TO service_role;

INSERT INTO agent.threads (
    id,
    agent_user_id,
    owner_user_id,
    model,
    cwd,
    status,
    run_status,
    is_main,
    branch_index,
    last_active_at,
    created_at,
    updated_at
)
SELECT
    t.id,
    t.agent_user_id,
    u.owner_user_id,
    t.model,
    t.cwd,
    t.status,
    'idle',
    (t.is_main <> 0),
    t.branch_index,
    CASE WHEN t.last_active_at IS NULL THEN NULL ELSE to_timestamp(t.last_active_at) END,
    to_timestamp(t.created_at),
    CASE WHEN t.updated_at IS NULL THEN to_timestamp(t.created_at) ELSE to_timestamp(t.updated_at) END
FROM staging.threads t
JOIN staging.users u ON u.id = t.agent_user_id
WHERE u.owner_user_id IS NOT NULL;

INSERT INTO agent.thread_tasks (
    thread_id,
    task_id,
    subject,
    description,
    status,
    active_form,
    owner,
    blocks,
    blocked_by,
    metadata
)
SELECT
    thread_id,
    task_id,
    subject,
    description,
    status,
    active_form,
    owner,
    blocks,
    blocked_by,
    metadata
FROM staging.agent_thread_tasks
;

DO $$
DECLARE
    v_source_threads integer;
    v_target_threads integer;
    v_source_tasks integer;
    v_target_tasks integer;
BEGIN
    SELECT count(*)
    INTO v_source_threads
    FROM staging.threads t
    JOIN staging.users u ON u.id = t.agent_user_id
    WHERE u.owner_user_id IS NOT NULL;

    SELECT count(*) INTO v_target_threads FROM agent.threads;

    IF v_target_threads <> v_source_threads THEN
        RAISE EXCEPTION 'agent.threads parity failed: source %, target %', v_source_threads, v_target_threads;
    END IF;

    SELECT count(*) INTO v_source_tasks FROM staging.agent_thread_tasks;
    SELECT count(*) INTO v_target_tasks FROM agent.thread_tasks;

    IF v_target_tasks <> v_source_tasks THEN
        RAISE EXCEPTION 'agent.thread_tasks parity failed: source %, target %', v_source_tasks, v_target_tasks;
    END IF;
END $$;

COMMIT;
