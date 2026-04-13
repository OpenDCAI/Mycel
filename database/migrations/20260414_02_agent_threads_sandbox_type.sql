-- Database Refactor 02A corrective migration: add agent.threads.sandbox_type.
--
-- Scope:
-- - Add the current runtime-required sandbox_type column to agent.threads.
-- - Backfill values from staging.threads by thread id.
-- - Prove every target row was backfilled before enforcing NOT NULL.
--
-- Non-goals:
-- - No runtime repository routing.
-- - No mutation or deletion of public.* / staging.*.
-- - No default value and no application fallback. Future writes must provide
--   sandbox_type explicitly through the current thread creation contract.
-- - No container/workspace ontology expansion in this corrective slice.

BEGIN;

DO $$
DECLARE
    v_agent_threads_count integer;
    v_existing_column_count integer;
    v_missing_source_count integer;
    v_reverse_missing_count integer;
BEGIN
    SELECT count(*)
    INTO v_agent_threads_count
    FROM information_schema.tables
    WHERE table_schema = 'agent'
      AND table_name = 'threads';

    IF v_agent_threads_count <> 1 THEN
        RAISE EXCEPTION 'Cannot correct 02A: agent.threads does not exist';
    END IF;

    SELECT count(*)
    INTO v_existing_column_count
    FROM information_schema.columns
    WHERE table_schema = 'agent'
      AND table_name = 'threads'
      AND column_name = 'sandbox_type';

    IF v_existing_column_count <> 0 THEN
        RAISE EXCEPTION 'Cannot correct 02A: agent.threads.sandbox_type already exists';
    END IF;

    SELECT count(*)
    INTO v_missing_source_count
    FROM agent.threads a
    LEFT JOIN staging.threads s ON s.id = a.id
    WHERE s.id IS NULL
       OR s.sandbox_type IS NULL
       OR btrim(s.sandbox_type) = '';

    IF v_missing_source_count <> 0 THEN
        RAISE EXCEPTION 'Cannot correct agent.threads.sandbox_type: % target rows lack source sandbox_type', v_missing_source_count;
    END IF;

    SELECT count(*)
    INTO v_reverse_missing_count
    FROM staging.threads s
    LEFT JOIN agent.threads a ON a.id = s.id
    WHERE a.id IS NULL;

    IF v_reverse_missing_count <> 0 THEN
        RAISE EXCEPTION 'Cannot correct agent.threads.sandbox_type: % staging rows lack agent target row', v_reverse_missing_count;
    END IF;
END $$;

ALTER TABLE agent.threads
    ADD COLUMN sandbox_type TEXT;

UPDATE agent.threads a
SET sandbox_type = s.sandbox_type
FROM staging.threads s
WHERE s.id = a.id;

DO $$
DECLARE
    v_null_count integer;
BEGIN
    SELECT count(*)
    INTO v_null_count
    FROM agent.threads
    WHERE sandbox_type IS NULL
       OR btrim(sandbox_type) = '';

    IF v_null_count <> 0 THEN
        RAISE EXCEPTION 'agent.threads.sandbox_type backfill failed: % rows remain blank', v_null_count;
    END IF;
END $$;

ALTER TABLE agent.threads
    ALTER COLUMN sandbox_type SET NOT NULL;

COMMIT;
