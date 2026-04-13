# Database Refactor 02A Sandbox Type Correction Packet

Date: 2026-04-14

## Why This Exists

`agent.threads` was landed in 02A without `sandbox_type`.

That is a schema/runtime contract mismatch, not a UI issue:

- current `SupabaseThreadRepo` reads `sandbox_type` as part of the thread row contract
- current `/api/threads` returns a `sandbox` field derived from `sandbox_type`
- current runtime pool keys use `thread_id:sandbox_type`

Routing runtime repos to `agent.threads` without this column would force an application fallback/default shim. That is explicitly disallowed for this checkpoint.

## Narrow Decision

Add `agent.threads.sandbox_type` as a corrective column copied from `staging.threads.sandbox_type`.

This packet does not decide the final sandbox/container ontology. The meeting summary makes clear that `workspace` is only a thin working-directory context; the core runtime relation is thread to sandbox/container execution. `sandbox_type` may later be replaced by that stronger relation, but current 02A runtime routing still needs the current explicit field.

## Artifacts

- Precheck: `database/prechecks/20260414_02_agent_threads_sandbox_type_readonly.sql`
- Migration: `database/migrations/20260414_02_agent_threads_sandbox_type.sql`
- Rollback: `database/rollbacks/20260414_02_agent_threads_sandbox_type.sql`

## Preconditions

The read-only precheck must show:

- `agent.threads` exists exactly once
- `agent.threads.sandbox_type` does not already exist
- `staging.threads.sandbox_type` exists and is text-compatible
- every `agent.threads` row has a matching `staging.threads.sandbox_type`
- row sets still match between `agent.threads` and `staging.threads`

## Execution Plan

1. Run the read-only precheck.
2. Execute `database/migrations/20260414_02_agent_threads_sandbox_type.sql`.
3. Verify `agent.threads.sandbox_type` exists, is `NOT NULL`, and row count remains unchanged.
4. Verify service-role REST can select `id,sandbox_type` from `agent.threads`.

## Stoplines

- If any target row lacks a source `sandbox_type`, stop. Do not invent a default.
- If `agent.threads.sandbox_type` already exists, stop. Do not make the migration idempotent.
- If source/target row sets differ, stop. Do not route runtime repos.
- Do not add runtime fallbacks, defaults, or schema routing in this packet.

## Post-Execution Proof Required

After Ledger authorizes execution and the migration runs, append proof to `docs/database-refactor/02a-execution-proof.md`:

- precheck result summary
- migration result
- `information_schema.columns` proof for `agent.threads.sandbox_type`
- source/target row parity
- service-role REST proof selecting `id,sandbox_type`
