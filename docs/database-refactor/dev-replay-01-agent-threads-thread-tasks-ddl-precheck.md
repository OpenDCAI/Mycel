# Database Refactor Dev Replay 01: Agent Threads And Thread Tasks

## Goal

Codify the first dev-based landing packet for `agent.threads` and `agent.thread_tasks` without replaying stale PR #507 runtime surfaces.

This slice is deliberately DDL/precheck/rollback only. It does not route runtime repositories, add schedules, mutate existing `public.*` or `staging.*`, or create compatibility shims.

## Current Live Proof

Read-only proof was run on 2026-04-14 through the private Supavisor session tunnel using the ops-recorded tenant-user connection shape. No secrets were printed or stored in this repo.

Observed schemas and tables:

- schemas: `agent`, `public`, `staging`
- target tables already present: `agent.threads`, `agent.thread_tasks`
- later target tables already present: `agent.schedules`, `agent.schedule_runs`
- legacy/source tables still present: `public.threads`, `public.tool_tasks`, `staging.threads`, `staging.agent_thread_tasks`, `staging.users`

Observed row counts:

- `staging.threads`: 81
- `agent.threads`: 83
- `staging.agent_thread_tasks`: 274
- `agent.thread_tasks`: 274

Source-shape checks:

- owner derivation missing: 0
- duplicate `(agent_user_id, branch_index)` pairs in `staging.threads`: 0
- unsupported `staging.threads.status`: 0
- blank `staging.threads.sandbox_type`: 0
- unsupported `staging.agent_thread_tasks.status`: 0
- required nulls in `staging.agent_thread_tasks`: 0

Important mismatch:

- `agent.threads` has 2 target-only rows that are not in `staging.threads`; both are YATU/proof rows.
- Every current thread-task row uses `thread_id = 'test-deferred-execution'`, so all 274 rows are orphaned against both `staging.threads` and `agent.threads`.

This means current live has already been advanced past the fresh first-run migration shape, likely by the historical PR #507 work. The migration in this packet is still useful as a clean replay artifact for fresh environments, but it must not be executed blindly against current live.

## Files

- `database/prechecks/20260414_01_agent_threads_thread_tasks_readonly.sql`
- `database/migrations/20260414_01_agent_threads_thread_tasks.sql`
- `database/rollbacks/20260414_01_agent_threads_thread_tasks.sql`

## Migration Stance

The migration is first-run-only:

- it fails if schema `agent` already exists
- it creates `agent.threads` with `sandbox_type` from the start
- it copies `staging.threads` through `staging.users.owner_user_id`
- it copies `staging.agent_thread_tasks`
- it intentionally does not add an FK from `agent.thread_tasks.thread_id` to `agent.threads.id`
- it grants only `service_role`

No `IF NOT EXISTS`, `ON CONFLICT`, or compatibility fallback is used.

## Current Live Stopline

Do not execute this migration on current live as-is. Current live already contains `agent.*` objects and extra schedule tables. The correct next live-facing checkpoint is a validation/cleanup checkpoint, not a first-run DDL execution.

Candidate next checkpoint:

- verify whether the two target-only YATU threads should be removed or preserved as proof residue
- decide whether the 274 `test-deferred-execution` thread-task rows are legacy test residue and should be deleted
- decide how migration state should be represented for a live DB that was manually advanced before this dev replay PR

## Proof Plan

Before any execution in a fresh environment:

1. Run `database/prechecks/20260414_01_agent_threads_thread_tasks_readonly.sql`.
2. Confirm source checks are zero except the known orphan thread-task count.
3. Confirm `agent` schema is absent.
4. Execute `database/migrations/20260414_01_agent_threads_thread_tasks.sql`.
5. Verify service-role REST visibility for `agent.threads` and `agent.thread_tasks`.
6. Do not claim product closure; this is metadata/SQL proof only.

Backend API YATU and frontend Playwright CLI YATU belong to later runtime-routing checkpoints.
