# Evaluation Operator Truth Design

**Goal:** Restore an honest monitor-facing evaluation truth surface before any evaluation UI comeback, so monitor can report real evaluation state instead of hardcoded placeholders.

## Why This Exists

- The monitor revival sequence is now split into explicit PRs instead of one oversized frontend transplant.
- `PR-C1/#262` restored the shell and current mounted monitor routes.
- `PR-C2/#263` rebound the mounted monitor surfaces into that shell.
- Evaluation is different from those surfaces:
  - service-level operator truth still exists
  - the current monitor router does not expose a real evaluation route
  - the current dashboard still hardcodes `evaluations_running = 0` and `latest_evaluation = None`
- A visible evaluation page without truthful runtime backing would just recreate another shell-first fake surface.

This design defines the first evaluation recovery slice as a backend/operator-truth lane, not a frontend revival lane.

## Current Facts

- `backend/web/services/monitor_service.py` still contains `build_evaluation_operator_surface(...)`.
- Existing unit coverage already locks three important operator states:
  - bootstrap failure before thread rows materialize
  - running while waiting for threads
  - completed with recorded errors
- Current monitor public routes do not expose `/api/monitor/evaluation` or `/api/monitor/evaluations`.
- Current dashboard summary still returns:
  - `evaluations_running: 0`
  - `latest_evaluation: None`
- Historical evaluation/frontend anchors still exist in git history:
  - `3a7c7984` `feat: clarify provisional evaluation operator state`
  - `16059ddb` `feat: tighten evaluation status density`
  - `ea096f32` `feat: tighten monitor evaluation split density`

## Constraints

- Do not widen into evaluation runtime activation in this PR.
- Do not widen into monitor shell/frontend work; that belongs to the `PR-C*` line.
- Do not reopen product-facing routes.
- Do not invent a fake evaluation list if only one truthful operator surface exists today.
- Fail loudly when evaluation runtime truth is unavailable; do not silently return placeholders.

## Proposal Comparison

### Proposal A: Dashboard-only truth patch

- Keep evaluation data embedded only in `/api/monitor/dashboard`.
- Replace hardcoded placeholders with live values.

Pros:
- Smallest possible change.

Cons:
- Dashboard becomes the only evaluation truth surface.
- Future evaluation UI would have to reverse-extract detail from a summary endpoint.
- Mixes dashboard summary concerns with evaluation operator detail.

### Proposal B: Dedicated operator route first

- Introduce a dedicated monitor evaluation truth route.
- Let dashboard consume only a compact summary from that truth source.

Pros:
- Clean separation between summary and operator detail.
- Gives future evaluation UI a stable source of truth.
- Keeps dashboard lightweight.

Cons:
- Slightly more design work because route and payload need to be defined now.

### Proposal C: Full evaluation comeback

- Restore route, dashboard summary, monitor page, and runtime activation in one pass.

Why it loses:
- Blends backend truth, frontend revival, and runtime recovery into one PR.
- Makes review and blame isolation poor.
- Repeats the same overscope pattern that already hurt earlier lanes.

## Chosen Direction

Use Proposal B.

`PR-D1` should introduce a dedicated monitor evaluation truth route first, then let dashboard consume a compact summary from that source.

This keeps the work mergeable and creates a stable base for:

1. `PR-D1` evaluation operator truth
2. `PR-D2` evaluation monitor surface
3. `PR-D3` evaluation runtime activation

## Sequence Of PRs

### `PR-D1` evaluation operator truth

**Goal**
- Expose a truthful monitor evaluation route and remove dashboard's hardcoded evaluation placeholders.

**Includes**
- dedicated monitor evaluation route
- payload contract for operator truth
- dashboard summary fields derived from the same truth source
- integration and unit coverage for route behavior

**Does not include**
- monitor evaluation page/nav
- runtime runner repair or activation
- trace UI

### `PR-D2` evaluation monitor surface

**Goal**
- Mount evaluation inside the revived monitor shell using the truth route from `PR-D1`.

**Includes**
- monitor evaluation page
- shell navigation entry if route support is real
- operator-facing rendering of facts, artifacts, and next steps

### `PR-D3` evaluation runtime activation

**Goal**
- Make evaluation truly runnable again.

**Includes**
- runtime execution truth
- runner / summary / traces / thread materialization recovery
- coordination with the upstream owner where the runtime seam crosses identity/core changes

## `PR-D1` Route Design

### Primary route

- `GET /api/monitor/evaluation`

This route should return the current operator truth surface for the latest relevant evaluation run. It is intentionally singular unless the runtime source already supports a truthful list.

### Dashboard summary

`GET /api/monitor/dashboard` should keep only summary-level evaluation fields:

- `workload.evaluations_running`
- `latest_evaluation`

`latest_evaluation` should be a reduced summary derived from the operator truth route, not a second handcrafted logic branch.

## `PR-D1` Payload Shape

### Operator truth payload

Recommended shape:

```json
{
  "status": "running",
  "kind": "running_active",
  "tone": "default",
  "headline": "Evaluation is actively running.",
  "summary": "Thread rows and traces may lag behind the runner. Use live progress and logs before declaring drift.",
  "facts": [],
  "artifacts": [],
  "artifact_summary": {
    "present": 0,
    "missing": 0,
    "total": 0
  },
  "next_steps": [],
  "raw_notes": "runner=direct rc=0 ..."
}
```

`build_evaluation_operator_surface(...)` already defines most of this contract. `PR-D1` should formalize it as route output, not reinvent it.

### Dashboard summary payload

Recommended `latest_evaluation` summary shape:

```json
{
  "status": "running",
  "kind": "running_active",
  "tone": "default",
  "headline": "Evaluation is actively running."
}
```

The dashboard summary should stay intentionally small.

## Data Sources

`PR-D1` must identify one truthful source for:

- current evaluation status
- notes / runner facts
- score gate
- artifact paths
- thread counts

If the source does not exist or cannot be resolved, the route must fail honestly instead of returning `None` placeholders.

The first PR in this lane should prefer existing monitor/runtime truth over inventing a new store.

## Error Handling

- If no evaluation source exists yet, return an explicit `unavailable` operator payload, not fake emptiness.
- If evaluation notes exist but the operator surface cannot be derived, fail loudly.
- Dashboard must not silently swallow evaluation lookup failures and regress to `0 / None`.

`PR-D1` should choose this exact split:

- source absent or runtime intentionally unavailable:
  - `GET /api/monitor/evaluation` returns a truthful `unavailable` operator payload
  - dashboard derives summary from that explicit unavailable truth
- source present but operator payload derivation fails:
  - fail the route loudly
  - do not replace the failure with `None` or a fake empty payload

## Testing

### Existing unit truth that must stay green

- bootstrap failure before threads materialize
- running while waiting for threads
- completed with recorded errors

### New `PR-D1` coverage

- integration smoke for `GET /api/monitor/evaluation`
- integration proof that dashboard no longer hardcodes:
  - `evaluations_running = 0`
  - `latest_evaluation = None`
- negative-path proof for missing/unavailable evaluation truth

## Non-goals

- No shell/navigation work
- No evaluation density polish
- No evaluation route list view unless truthful source already exists
- No runtime activation claims
- No product app work

## Verification

Minimum bar for `PR-D1`:

- targeted unit tests around operator truth remain green
- new route integration tests green
- dashboard integration test proves evaluation fields come from real truth, not placeholders

## Risk Notes

- The main risk is inventing a route before confirming a truthful runtime source.
- The second risk is letting dashboard continue to own evaluation semantics directly.
- `PR-D1` should therefore keep the operator route authoritative and the dashboard derivative.
