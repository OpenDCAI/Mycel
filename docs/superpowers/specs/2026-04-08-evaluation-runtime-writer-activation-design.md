# Evaluation Runtime Writer Activation Design

## Goal

Turn evaluation truth from terminal-only persisted history into live writer-backed runtime truth, without widening into UI, product behavior, or a schema-heavy redesign.

## Current Facts

- `PR-D3a/#266` already makes monitor read persisted eval truth from:
  - `eval.storage.TrajectoryStore`
  - `storage.container.StorageContainer.eval_repo()`
  - `storage.providers.supabase.eval_repo.SupabaseEvalRepo`
  - `eval_runs / eval_metrics`
- `backend/web/services/streaming_service.py` currently writes eval truth only once, after run completion:
  - `TrajectoryStore().save_trajectory(trajectory)`
- current persisted rows are truthful for:
  - no runs
  - latest completed run
  - latest terminal error/cancelled run, if written
- current persisted rows are not truthful for:
  - live in-flight runs before completion
  - progress during retries / cancellation / error transitions
- `TrajectoryTracer` currently generates its own trajectory id late and `streaming_service` already has an earlier `run_id`.
- current repo contracts only support terminal inserts:
  - `save_trajectory(...)`
  - `save_metrics(...)`
  - no run-start write
  - no row update/finalize API

## Scope Check

`PR-D3b` must stay narrow. If it grows into one lane, it will mix:

- writer-side live activation
- monitor truth semantics
- richer artifact/model/thread drilldown
- frontend claims

That is the same failure mode that previously made monitor/evaluation work too large to merge safely.

So `PR-D3b` must only do writer-side live activation for the existing persisted source.

## Approaches

### 1. In-place `eval_runs` lifecycle writes

Use the existing `eval_runs` row as the single source of truth for both live and terminal state:

- create or upsert a `running` row at run start
- update the same row on cancellation / error / completion
- continue writing metrics separately

Pros:
- no second source contract
- no new table
- monitor continues reading the same path as `PR-D3a`
- smallest blast radius

Cons:
- only coarse live truth unless more fields are added later
- requires careful upsert/finalize semantics across SQLite and Supabase

Recommended.

### 2. Separate live snapshot table

Introduce a second table for live status and let monitor merge it with terminal history.

Pros:
- clean separation between live and historical data

Cons:
- new schema surface
- monitor now has to reconcile two sources
- much larger than this lane needs

Not recommended.

### 3. Revive old manifest/artifact contract now

Reintroduce `run_dir`, `manifest_path`, `trace_summaries_path`, and thread-materialization counters as part of live activation.

Pros:
- closer to the older operator formatter shape

Cons:
- current runtime does not already produce those fields truthfully
- forces `PR-D3b` to invent new writer semantics and larger storage shape
- too much scope for one lane

Rejected for this slice.

## Recommended Design

`PR-D3b` should activate live truth by making the existing persisted row appear earlier and advance in place.

The concrete shape is:

- run start:
  - persist a `running` row immediately using the known `run_id`
  - include:
    - `id`
    - `thread_id`
    - `started_at`
    - `status=running`
    - `user_message`
- run completion:
  - finalize the same row with:
    - `finished_at`
    - `final_response`
    - `status`
    - `run_tree_json`
    - `trajectory_json`
- terminal error / cancellation:
  - finalize the same row with terminal status even if the normal completion path is skipped
- metrics:
  - continue writing through existing `save_metrics(...)`
  - do not invent new metric tiers in this slice

## Data Model Decisions

### Stable run identity

`PR-D3b` should stop relying on “trajectory id appears only at terminal serialization time”.

Use one stable id across the full run lifecycle:

- `streaming_service` already has `run_id`
- `TrajectoryTracer` should accept and preserve that same `run_id`
- persisted `eval_runs.id` should therefore line up with the web runtime run id

This avoids “start row id” and “completed row id” drifting apart.

### Writer semantics

Add minimal repo operations for lifecycle truth:

- `upsert_run_header(...)`
  - for run start / coarse live status
- `finalize_run(...)`
  - for terminal state on the same row

Terminal call/tool rows remain terminal-only in this slice. Do not attempt incremental live persistence for them yet.

### Failure semantics

Live writer activation must fail loudly:

- if run-start persistence fails:
  - log loudly
  - do not silently fake that live truth exists
- if terminal finalize fails:
  - log loudly
  - the row may remain stale as `running`, which is preferable to fake cleanup

This lane is about making source truth real, not making it cosmetically pleasant.

## Implementation Boundaries

### In scope for `PR-D3b`

- stable run id reuse between `streaming_service` and `TrajectoryTracer`
- repo methods for run-start upsert and terminal finalize
- SQLite + Supabase parity for those methods
- write-path activation in `streaming_service`
- tests proving:
  - live `running` row is written before terminal completion
  - terminal completion reuses the same row
  - cancellation/error finalize the same row truthfully

### Out of scope for `PR-D3b`

- frontend changes
- monitor route changes
- product-facing evaluation behavior
- new tables or migrations beyond the smallest repo contract change
- richer artifact/log/thread drilldown
- trace-level detail persistence during live execution

## Testing

### Unit

- repo parity tests for new lifecycle methods
- `TrajectoryTracer` tests proving stable id reuse
- streaming writer tests for:
  - run-start write
  - terminal finalize
  - cancellation/error finalize

### Integration

- route-level proof that monitor can observe a `running` eval row before terminal completion
- route-level proof that terminal completion updates the same row id

## Merge Bar

`PR-D3b` is done when:

- a run writes `running` truth before completion
- completion/cancellation/error update the same persisted row id
- `PR-D3a` monitor reader can now observe live-vs-terminal truth through the same source path
- no UI/product/schema sprawl was mixed in
