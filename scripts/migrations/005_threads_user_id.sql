-- Migration 005: add user_id column to public.threads
-- Applied to production: 2026-04-07
--
-- public.threads was missing user_id (only staging.threads had it).
-- After schema isolation removal (commit 9005c588), messaging routes that
-- resolve thread→social-user mappings would 500 on public schema.
--
ALTER TABLE threads ADD COLUMN IF NOT EXISTS user_id TEXT;
