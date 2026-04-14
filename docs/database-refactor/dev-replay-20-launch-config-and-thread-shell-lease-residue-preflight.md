# Database Refactor Dev Replay 20: Launch Config And Thread Shell Lease Residue Preflight

## Goal

Decide the next narrow cleanup boundary for the remaining `lease_id` residue in
the thread-create / launch-config shell.

This checkpoint is doc/ruling only. It does not change request models,
frontend payloads, backend behavior, runtime managers, SQL/migrations, or live
DB state.

## Why This Comes Next

Replay-18 and replay-19 finished the current-workspace null-fencing line:

- explicit historical/read-compat null rows are fenced as legacy residue
- helper/test-only create looseness has been tightened

That leaves a different residue family:

- `lease_id` still appears in thread-create request shells and launch-config
  payloads even though backend truth for thread binding has already shifted to
  thread-owned `current_workspace_id`

The next ambiguity is no longer about nullability. It is about whether the
shell still exposes `lease_id` as if it were native truth, or whether it is
now just a temporary ingress/round-trip field around a different backend
authority.

## Linkage

- replay-13 made owner-facing thread create write `current_workspace_id`
- replay-14 and replay-15 established that launch-config persistence is
  metadata and that backend default resolution should derive from thread-owned
  bridge truth rather than lease-first coincidence
- replay-18 and replay-19 fenced the remaining nullable current-workspace
  residue without widening into shell cleanup

So replay-20 should return to the launch-config / thread shell residue that was
intentionally deferred earlier.

## Current Code Facts

### 1. Request models still expose `lease_id`

`backend/web/models/requests.py` still carries `lease_id` in thread-related
request models.

That means the owner-facing shell still speaks lease-shaped input directly.

### 2. Thread router still treats `payload.lease_id` as the existing-resource selector

`backend/web/routers/threads.py` still branches on `payload.lease_id` for the
"existing lease" path and maps it to `current_workspace_id`.

This may still be acceptable as ingress residue, but it should now be named
and fenced honestly.

### 3. Launch-config service still stores and round-trips `lease_id`

`backend/web/services/thread_launch_config_service.py` still normalizes,
persists, and returns `lease_id`.

After replay-15, this no longer means lease-first is backend truth. But the
shell still looks lease-shaped.

### 4. Frontend API contract still models launch-config as lease-shaped

`frontend/app/src/api/client.ts` and `frontend/app/src/api/types.ts` still
encode/decode launch-config payloads with `lease_id`.

This is a shell contract question, not a runtime/monitor question.

## Explicit Frontend Classification

Replay-20 must classify the frontend `lease_id` surfaces explicitly instead of
talking about "frontend residue" as one blob.

### Thread shell / launch-config residue

These frontend surfaces are in replay-20 scope because they are part of the
owner-facing thread-create or launch-config shell:

1. `frontend/app/src/api/client.ts`

- `CreateThreadOptions.leaseId`
- `createThread(...)` writing `body.lease_id`
- `parseThreadLaunchConfig(...)` reading `payload.lease_id`
- `saveDefaultThreadConfig(...)` round-tripping `ThreadLaunchConfig`

2. `frontend/app/src/api/types.ts`

- `ThreadLaunchConfig.lease_id?: string | null`

These are the places where shell-level lease selection still appears in the
API/UI contract even though backend thread-binding truth has moved elsewhere.

### Legitimate runtime/resource identity

These frontend/API surfaces are **not** replay-20 residue just because they
contain `lease_id`. They describe real resource/runtime identity:

1. `frontend/app/src/api/types.ts`

- `UserLeaseSummary.lease_id`
- `TerminalStatus.lease_id`
- `LeaseStatus.lease_id`

2. `frontend/app/src/api/client.ts`

- `parseUserLeases(...)`
- `parseTerminalStatus(...)`
- `parseLeaseStatus(...)`

These should stay out of replay-20. They are reporting or parsing real lease
objects, not modeling the thread-create / launch-config shell.

## Important Non-Goal

Replay-20 must not confuse two different categories of `lease_id`.

### Legitimate runtime/resource identity

These are not replay-20 targets:

- monitor/resource overview/detail surfaces
- sandbox/lease status surfaces
- runtime/session/terminal/lease records where `lease_id` is the real resource
  identity

Those uses are not residue just because they mention leases.

### Thread shell / launch-config residue

This **is** replay-20 territory:

- owner-facing create-thread shell
- launch-config persistence / payload shape
- frontend thread-create config UI/API contract

The question here is whether lease-shaped shell fields are still the right
temporary ingress, or whether they now obscure the real authority too much.

## The Actual Ambiguity

There are three possible interpretations of today's shell-level `lease_id`:

### A. It is still native truth for thread binding

This is likely false now, because thread binding truth has already moved to
thread-owned `current_workspace_id`.

### B. It is tolerated only as an ingress/round-trip shell field

This means:

- users can still pick an existing lease by `lease_id`
- backend may still echo/save that field for shell continuity
- but it is no longer the backend authority for thread binding

### C. It is already harmful enough that the next slice should remove or rename it

This may eventually be true, but replay-20 should first decide whether the next
slice belongs in backend shell semantics only, or whether it must widen into
frontend/request contract cleanup.

## Recommended Ruling

### 1. Treat shell-level `lease_id` as residue, not backend authority

Replay-20 should explicitly state:

- thread binding truth is not `lease_id`
- shell-level `lease_id` is, at most, a temporary selector / round-trip field
  around thread-owned bridge truth

### 2. Separate backend-shell cleanup from frontend/request-contract cleanup

The next implementation checkpoint should prefer the smallest honest slice.

The first question is not "remove `lease_id` everywhere".
The first question is:

- can backend shell semantics be tightened further while request/frontend shape
  stays temporarily stable?

### 3. Keep monitor/runtime lease identity out of lane

Replay-20 should explicitly reject any attempt to clean up monitor/runtime
`lease_id` references under the same banner. Those are separate concepts.

## Proposed Next Implementation Candidates

Replay-20 should evaluate these two candidate directions and choose one in the
ruling.

### Candidate 1: backend-shell-only tightening

Target:

- keep request/frontend payload shape unchanged for now
- tighten backend launch-config / router semantics so `lease_id` is treated
  explicitly as ingress/round-trip residue, not native truth

Pros:

- narrower
- aligns with replay-15 style
- less likely to widen into frontend churn

### Candidate 2: request/frontend shell contract cleanup

Target:

- start renaming/remapping request and frontend payloads away from `lease_id`

Pros:

- cleaner long-term surface

Cons:

- wider
- couples backend truth cleanup with UI/API contract movement
- more likely to spill into unrelated shell churn

## Recommendation

Prefer Candidate 1 first.

Reason:

- backend authority has already moved
- the next minimal step is to make backend shell semantics more honest before
  forcing a frontend/request contract rewrite

## Proposed First Implementation Checkpoint After Replay-20

`database-refactor-dev-replay-21-launch-config-backend-shell-residue-tightening`

Intended boundary:

- backend shell semantics only
- no frontend/request payload redesign yet
- no runtime/monitor work

## Stopline

Replay-20 does **not** authorize:

- changing request model fields yet
- changing frontend payload/types yet
- changing monitor/runtime/resource surfaces
- changing storage contracts or runtime binding readers
- SQL/migrations/live DB writes
- historical row repair

## Open Question For Ledger Ruling

Is replay-20 the right checkpoint to formally classify shell-level `lease_id`
as temporary ingress/round-trip residue and to bias the next implementation
slice toward backend-shell-only tightening rather than frontend/request contract
cleanup?
