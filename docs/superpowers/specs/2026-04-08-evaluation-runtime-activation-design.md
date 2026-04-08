# Evaluation Runtime Activation Design

## Goal

Turn monitor evaluation from a hardcoded `unavailable` placeholder into a truthful runtime-backed operator surface, without collapsing route truth, UI truth, and runner implementation into one giant PR.

## Current Facts

- `PR-D1/#264` already exposed `GET /api/monitor/evaluation`.
- `PR-D2/#265` already mounted `/evaluation` in the revived monitor shell.
- `backend/web/services/monitor_service.py` already defines the target operator payload shape through `build_evaluation_operator_surface(...)`.
- That same service currently hardcodes `get_monitor_evaluation_truth()` to `_evaluation_unavailable_surface()`.
- The repo already persists completed eval runs through:
  - `eval.storage.TrajectoryStore`
  - `storage.container.StorageContainer.eval_repo()`
  - `storage.providers.supabase.eval_repo.SupabaseEvalRepo`
- `backend/web/services/streaming_service.py` already writes trajectories into that store after a run completes.
- The persisted source currently carries:
  - coarse run status
  - timestamps
  - thread id
  - user message
  - trajectory JSON
  - tiered metrics rows
- It does not currently carry the older manifest/log/thread-materialization fields that `build_evaluation_operator_surface(...)` was designed around.
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

### 3. Repo-backed persisted-truth activation

Use the existing `TrajectoryStore -> eval_repo -> eval_runs/eval_metrics` path as the first truthful runtime source, and let monitor read the latest persisted run from there.

Pros:
- already exists on latest `dev`
- stays in the same Supabase-backed storage world as the web runtime
- avoids inventing a second source contract before proving the first one
- allows a narrow first mergeable slice

Cons:
- current writes happen after run completion, so this does not expose live in-flight eval progress yet
- does not carry legacy `run_dir / manifest / trace summary / thread-materialization` detail

Recommended.

## Recommended Design

`PR-D3` becomes a 3-step workstream:

### PR-D3a: Persisted source truth hookup

Introduce a narrow reader for “latest persisted evaluation run” and make `get_monitor_evaluation_truth()` read it instead of hardcoding `unavailable`.

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

Use the existing persisted eval contract:

- `eval_runs`
  - `id`
  - `thread_id`
  - `started_at`
  - `finished_at`
  - `status`
  - `user_message`
  - `trajectory_json`
- `eval_metrics`
  - tiered metric rows keyed by `run_id`

`PR-D3a` only promises truthful consumption of what is already persisted there. It does not pretend the old manifest/log/thread-materialization fields still exist.

### Monitor hookup

`get_monitor_evaluation_truth()` should:

1. read the latest persisted run from the eval repo
2. read that run's persisted metric rows
3. normalize the coarse persisted status into the monitor payload shape
4. fail loudly if repo reads or metric decoding break
5. return an explicit idle/no-runs payload only when the source is wired but empty

That keeps “no recorded runs yet” distinct from “broken source”.

### Failure semantics

- eval source wired but no recorded runs:
  - explicit `idle/no_recorded_runs`
- repo or decoding failure:
  - loud error, not fake unavailable
- persisted run present:
  - real repo-backed operator payload, with legacy artifact/thread fields explicitly absent

This is important because fake downgrades would hide actual activation bugs.

## PR-D3b Design

Once `PR-D3a` exposes repo-backed persisted truth, the runner side must evolve if we want live/in-flight operator truth.

Write moments for `PR-D3b`:

- run bootstrapped
- in-flight progress changes
- completion / failure

The write path should stay minimal, but it must stop waiting until terminal completion before persisting operator-relevant truth.

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

Do not redesign the whole operator surface to preserve an old artifact contract that current storage no longer writes.

`PR-D3a` should surface repo-backed truth directly and honestly. Richer formatter reuse or artifact revival belongs to later slices if still justified.

## Testing

### PR-D3a

- unit tests for no-runs and persisted-run cases
- integration tests for `/api/monitor/evaluation` and `/api/monitor/dashboard`

### PR-D3b

- write-path tests for lifecycle transitions
- proof that monitor sees updated truth after writes

### PR-D3c

- frontend tests only after drilldown exists

## Boundaries

### In scope for PR-D3a

- repo-backed persisted source hookup
- monitor truth hookup
- route-level truth upgrade from fake unavailable to real persisted-source payload

### Out of scope for PR-D3a

- monitor UI redesign
- product-facing evaluation UI
- trace drilldown
- schema-heavy persistence redesign

## Merge Bars

### PR-D3a

- `get_monitor_evaluation_truth()` reads a real persisted source
- no-runs vs persisted-run truth are distinct
- route tests prove `/api/monitor/evaluation` is no longer hardcoded

### PR-D3b

- real runner writes truthful source updates
- monitor reflects live or completed evaluation state

### PR-D3c

- optional operator drilldown only after stable runtime truth exists
