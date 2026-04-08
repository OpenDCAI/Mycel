# Evaluation Runtime Activation Design

## Goal

Turn monitor evaluation from a hardcoded `unavailable` placeholder into a truthful runtime-backed operator surface, without collapsing route truth, UI truth, and runner implementation into one giant PR.

## Current Facts

- `PR-D1/#264` already exposed `GET /api/monitor/evaluation`.
- `PR-D2/#265` already mounted `/evaluation` in the revived monitor shell.
- `backend/web/services/monitor_service.py` already defines the target operator payload shape through `build_evaluation_operator_surface(...)`.
- That same service currently hardcodes `get_monitor_evaluation_truth()` to `_evaluation_unavailable_surface()`.
- The repo currently contains almost no runtime source reader that can supply:
  - `status`
  - `notes`
  - `score_gate`
  - `run_dir`
  - `manifest_path`
  - `eval_summary_path`
  - `trace_summaries_path`
  - thread materialization counts
- Existing tests prove formatter behavior, not source discovery or runtime activation.

## Scope Check

`PR-D3` is too large to be one implementation PR.

If treated as one lane, it would mix:

- runtime source design
- runner write semantics
- monitor truth hookup
- operator page/live proof
- possible trace drilldown

That is exactly the failure mode that previously made monitor/frontend work too large to merge safely.

So `PR-D3` must be a workstream, not a single code drop.

## Approaches

### 1. DB-first activation

Add dedicated evaluation runtime tables and make monitor read from the database.

Pros:
- strong query surface
- durable

Cons:
- schema-heavy
- requires migration design
- much larger blast radius than the current monitor lane needs

Not recommended for the first activation slice.

### 2. In-process state activation

Keep evaluation runtime state only in memory and let monitor read it directly.

Pros:
- small initial implementation

Cons:
- dies on restart
- hard to inspect after failures
- does not fit the existing artifact/path-based operator payload shape

Rejected.

### 3. Filesystem/manifest-first activation

Define a minimal runtime source contract in files, have the evaluation runner write it, and have monitor read it.

Pros:
- matches the existing operator payload expectations (`run_dir`, `manifest_path`, logs, summaries)
- durable across process restarts
- keeps monitor truth and runner writes loosely coupled
- allows a narrow first mergeable slice

Recommended.

## Recommended Design

`PR-D3` becomes a 3-step workstream:

### PR-D3a: Runtime source contract + monitor truth hookup

Introduce a narrow runtime source contract for “latest evaluation run” and make `get_monitor_evaluation_truth()` read it instead of hardcoding `unavailable`.

This is the first mergeable slice.

### PR-D3b: Runner write-path activation

Make the actual evaluation runner write the runtime source truthfully while the run progresses and when it completes or fails.

### PR-D3c: Optional drilldown and deeper operator ergonomics

Only after source truth is stable:

- richer drilldown
- trace-level linking
- maybe detail pages or deeper artifact navigation

This is explicitly later.

## PR-D3a Design

### Runtime source contract

Use a small file-backed contract, rooted in a stable path under evaluation runtime storage.

Minimum fields:

- `status`
- `notes`
- `score`
  - `score_gate`
  - `publishable`
  - `scored`
  - `error_instances`
  - `run_dir`
  - `manifest_path`
  - `eval_summary_path`
  - `trace_summaries_path`
- `threads`
  - `total`
  - `running`
  - `done`
- `updated_at`

This contract should be sufficient to feed `build_evaluation_operator_surface(...)` without widening that formatter.

### Monitor hookup

`get_monitor_evaluation_truth()` should:

1. read the runtime source
2. validate the minimum shape
3. pass the extracted values into `build_evaluation_operator_surface(...)`
4. return loud failure if the source is malformed
5. return `unavailable` only when the runtime source is truly absent

That keeps “no source” distinct from “broken source”.

### Failure semantics

- source absent:
  - explicit `unavailable`
- source present but malformed:
  - loud error, not fake unavailable
- source present and valid:
  - real operator payload

This is important because fake downgrades would hide actual activation bugs.

## PR-D3b Design

Once `PR-D3a` defines the source contract, the runner side must write it.

Write moments:

- run bootstrapped
- threads materialized / counts changed
- score artifacts created
- run completed
- run failed early

The write path should stay minimal:

- one canonical latest-run file or manifest
- optional referenced artifact files

Do not introduce extra UI or schema work in this slice.

## PR-D3c Design

Only after `PR-D3a` and `PR-D3b` are stable:

- richer operator drilldown
- trace drill links
- maybe run history if a truthful source exists

This must stay separate from activation itself.

## Architecture

### Reader/writer split

Keep the boundary explicit:

- writer side: evaluation runtime / runner
- reader side: monitor service

Monitor should not infer missing runtime semantics on its own. It should read, validate, and format.

### Formatter reuse

Do not redesign `build_evaluation_operator_surface(...)` unless a real source gap forces it.

That formatter is already the most stable contract in this lane. Activation should feed it, not replace it.

## Testing

### PR-D3a

- unit tests for source-absent, malformed-source, and valid-source cases
- integration tests for `/api/monitor/evaluation` and `/api/monitor/dashboard`

### PR-D3b

- write-path tests for lifecycle transitions
- proof that monitor sees updated truth after writes

### PR-D3c

- frontend tests only after drilldown exists

## Boundaries

### In scope for PR-D3a

- source contract
- monitor truth hookup
- route-level truth upgrade from fake unavailable to real source-backed payload

### Out of scope for PR-D3a

- monitor UI redesign
- product-facing evaluation UI
- trace drilldown
- schema-heavy persistence redesign

## Merge Bars

### PR-D3a

- `get_monitor_evaluation_truth()` reads a real runtime source
- source absent vs malformed vs valid are distinct
- route tests prove `/api/monitor/evaluation` is no longer hardcoded

### PR-D3b

- real runner writes truthful source updates
- monitor reflects live or completed evaluation state

### PR-D3c

- optional operator drilldown only after stable runtime truth exists
