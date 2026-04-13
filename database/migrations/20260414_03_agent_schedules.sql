-- Database Refactor 02G: land agent.schedules and agent.schedule_runs.
--
-- Scope:
-- - Create agent.schedules.
-- - Create agent.schedule_runs.
-- - Grant service_role access.
--
-- Non-goals:
-- - No mutation or deletion of public.* / staging.*.
-- - No migration from cron_jobs because live public/staging cron_jobs are empty.
-- - No panel_tasks migration. Panel tasks are explicitly not target schedule ontology.
-- - No runtime repository routing.
-- - No /cron-jobs API behavior change.
-- - No frontend behavior change.
-- - No RLS/realtime policy in this migration. Add only after behavior is proved
--   in a separate checkpoint.

BEGIN;

DO $$
DECLARE
    v_agent_schema_count integer;
    v_agent_threads_count integer;
    v_schedules_count integer;
    v_schedule_runs_count integer;
    v_public_cron_jobs_count integer;
    v_staging_cron_jobs_count integer;
BEGIN
    SELECT count(*)
    INTO v_agent_schema_count
    FROM information_schema.schemata
    WHERE schema_name = 'agent';

    IF v_agent_schema_count <> 1 THEN
        RAISE EXCEPTION 'Cannot migrate 02G: agent schema must exist exactly once, found %', v_agent_schema_count;
    END IF;

    SELECT count(*)
    INTO v_agent_threads_count
    FROM information_schema.tables
    WHERE table_schema = 'agent'
      AND table_name = 'threads';

    IF v_agent_threads_count <> 1 THEN
        RAISE EXCEPTION 'Cannot migrate 02G: agent.threads must exist exactly once, found %', v_agent_threads_count;
    END IF;

    SELECT count(*)
    INTO v_schedules_count
    FROM information_schema.tables
    WHERE table_schema = 'agent'
      AND table_name = 'schedules';

    IF v_schedules_count <> 0 THEN
        RAISE EXCEPTION 'Cannot migrate 02G: agent.schedules already exists';
    END IF;

    SELECT count(*)
    INTO v_schedule_runs_count
    FROM information_schema.tables
    WHERE table_schema = 'agent'
      AND table_name = 'schedule_runs';

    IF v_schedule_runs_count <> 0 THEN
        RAISE EXCEPTION 'Cannot migrate 02G: agent.schedule_runs already exists';
    END IF;

    SELECT count(*) INTO v_public_cron_jobs_count FROM public.cron_jobs;
    SELECT count(*) INTO v_staging_cron_jobs_count FROM staging.cron_jobs;

    IF v_public_cron_jobs_count <> 0 OR v_staging_cron_jobs_count <> 0 THEN
        RAISE EXCEPTION
            'Cannot migrate 02G without a cron_jobs data ruling: public %, staging %',
            v_public_cron_jobs_count,
            v_staging_cron_jobs_count;
    END IF;
END $$;

CREATE TABLE agent.schedules (
    id                   TEXT        PRIMARY KEY,
    owner_user_id        TEXT        NOT NULL,
    agent_user_id        TEXT        NOT NULL,
    target_thread_id     TEXT,
    create_thread_on_run BOOLEAN     NOT NULL DEFAULT false,
    cron_expression      TEXT        NOT NULL,
    enabled              BOOLEAN     NOT NULL DEFAULT true,
    instruction_template TEXT        NOT NULL,
    timezone             TEXT        NOT NULL DEFAULT 'UTC',
    last_run_at          TIMESTAMPTZ,
    next_run_at          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT schedules_target_chk
        CHECK (target_thread_id IS NOT NULL OR create_thread_on_run),
    CONSTRAINT schedules_instruction_template_chk
        CHECK (btrim(instruction_template) <> ''),
    CONSTRAINT schedules_cron_expression_chk
        CHECK (btrim(cron_expression) <> ''),
    CONSTRAINT schedules_timezone_chk
        CHECK (btrim(timezone) <> '')
);

CREATE INDEX idx_schedules_owner_enabled_next_run
    ON agent.schedules(owner_user_id, next_run_at)
    WHERE enabled = true;

CREATE INDEX idx_schedules_agent
    ON agent.schedules(agent_user_id);

CREATE INDEX idx_schedules_target_thread
    ON agent.schedules(target_thread_id)
    WHERE target_thread_id IS NOT NULL;

CREATE TABLE agent.schedule_runs (
    id            TEXT        PRIMARY KEY,
    schedule_id   TEXT        NOT NULL,
    owner_user_id TEXT        NOT NULL,
    agent_user_id TEXT        NOT NULL,
    thread_id     TEXT,
    status        TEXT        NOT NULL DEFAULT 'queued',
    triggered_by  TEXT        NOT NULL,
    scheduled_for TIMESTAMPTZ,
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ,
    input_json    JSONB       NOT NULL DEFAULT '{}',
    output_json   JSONB       NOT NULL DEFAULT '{}',
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT schedule_runs_status_chk
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    CONSTRAINT schedule_runs_triggered_by_chk
        CHECK (triggered_by IN ('scheduler', 'manual'))
);

CREATE INDEX idx_schedule_runs_schedule_created
    ON agent.schedule_runs(schedule_id, created_at DESC);

CREATE INDEX idx_schedule_runs_owner_created
    ON agent.schedule_runs(owner_user_id, created_at DESC);

CREATE INDEX idx_schedule_runs_status_scheduled
    ON agent.schedule_runs(status, scheduled_for);

GRANT SELECT, INSERT, UPDATE, DELETE ON agent.schedules TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON agent.schedule_runs TO service_role;

DO $$
DECLARE
    v_schedules_count integer;
    v_schedule_runs_count integer;
BEGIN
    SELECT count(*)
    INTO v_schedules_count
    FROM information_schema.tables
    WHERE table_schema = 'agent'
      AND table_name = 'schedules';

    SELECT count(*)
    INTO v_schedule_runs_count
    FROM information_schema.tables
    WHERE table_schema = 'agent'
      AND table_name = 'schedule_runs';

    IF v_schedules_count <> 1 OR v_schedule_runs_count <> 1 THEN
        RAISE EXCEPTION '02G table creation parity failed: schedules %, schedule_runs %', v_schedules_count, v_schedule_runs_count;
    END IF;
END $$;

COMMIT;
