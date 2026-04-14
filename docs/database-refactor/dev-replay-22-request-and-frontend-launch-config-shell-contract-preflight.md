# Database Refactor Dev Replay 22: Request And Frontend Launch Config Shell Contract Preflight

## Goal

Decide the next narrow cleanup boundary for the remaining outward shell
contract that still exposes thread-create / launch-config selection as
`lease_id`.

This checkpoint is doc/ruling only. It does not change request models,
frontend behavior, backend behavior, runtime/resource surfaces, SQL/migrations,
or live DB state.

## Why This Comes Next

Replay-20 and replay-21 finished the backend-shell truth cleanup:

- shell-level `lease_id` was explicitly classified as residue, not backend
  authority
- backend launch-config normalization now drops effective `lease_id` for
  `create_mode="new"`

That means the next ambiguity is no longer inside backend helper truth. It is
the outward shell contract:

- request models still expose `lease_id`
- frontend API/types still expose `lease_id`
- `NewChatPage` still models existing-resource selection directly as
  `selectedLeaseId`

So replay-22 should decide how that outward shell should evolve now that the
backend no longer treats `lease_id` as native truth.

## Current Code Facts

### 1. Backend request models still expose shell-level `lease_id`

`backend/web/models/requests.py` still defines:

- `CreateThreadRequest.lease_id`
- `SaveThreadLaunchConfigRequest.lease_id`

Those are the backend request-side shell entry points.

### 2. Frontend API client/types still expose shell-level `lease_id`

`frontend/app/src/api/client.ts` still includes:

- `CreateThreadOptions.leaseId`
- `createThread(...)` writing `body.lease_id`
- `parseThreadLaunchConfig(...)` reading `payload.lease_id`

`frontend/app/src/api/types.ts` still includes:

- `ThreadLaunchConfig.lease_id?: string | null`

These are the frontend API contract surfaces for the same shell concept.

### 3. UI state in `NewChatPage` is still directly lease-shaped

`frontend/app/src/pages/NewChatPage.tsx` still uses:

- `selectedLeaseId`
- `leaseOptions`
- `config.lease_id`
- create-mode branching that writes `lease_id` into outgoing config

This means the UI is still naming the selector in lease-native terms.

### 4. Not every `lease_id` in frontend is residue

Replay-20 already established that these are **not** part of the shell cleanup:

- `UserLeaseSummary.lease_id`
- `TerminalStatus.lease_id`
- `LeaseStatus.lease_id`
- `parseUserLeases(...)`
- `parseTerminalStatus(...)`
- `parseLeaseStatus(...)`

Those describe real runtime/resource identity, not thread-create shell
selection.

## The Actual Ambiguity

There are at least three possible ways to move the outward shell next.

### A. Keep the outward shell lease-shaped indefinitely

This is easy, but now mismatched with backend truth. It risks preserving the
wrong mental model for future work.

### B. Rename the outward shell toward thread/bridge/workspace language

This would align the shell better with backend truth, but may still need an
existing-lease selector concept somewhere.

### C. Keep the user-facing concept as "existing sandbox/session" selection,
but stop presenting it as `lease_id` in the request/frontend contract

This looks like the most honest direction:

- preserve the user action: choose an existing runtime resource
- stop exposing raw `lease_id` as the first-class shell field name

## Recommended Ruling

### 1. The next lane should target outward shell contract cleanup

Replay-22 should explicitly say:

- backend-shell truth is now clean enough
- the next residue is outward shell naming/contract shape

### 2. Bias toward request/frontend contract cleanup together, not separately

Unlike replay-21, this lane probably should not split backend request models
and frontend API/types into separate checkpoints.

Reason:

- request model names and frontend payload names are one contract boundary
- changing only one side would mostly create temporary translation glue

### 3. Keep runtime/resource identity completely out of lane

Replay-22 must preserve the split:

- shell selection residue is in lane
- runtime/resource lease identity is out of lane

### 4. Prefer semantic rename over patchy alias sprawl

If replay-22 eventually renames outward fields, it should avoid a long-lived
"both names everywhere" state unless a short compatibility bridge is truly
required.

The target should be a cleaner shell, not a permanent bilingual contract.

## Proposed First Implementation Candidates

Replay-22 should compare two candidate directions.

### Candidate 1: API-contract-first cleanup

Target:

- rename/reshape request model fields and frontend API/types first
- update `NewChatPage` state/serialization in the same slice
- keep backend helper truth unchanged

Pros:

- aligns the outer shell with backend truth directly
- avoids adding more backend translation glue

Cons:

- wider than replay-21
- touches both backend request models and frontend app code

### Candidate 2: UI wording/state cleanup only

Target:

- keep request payload shape for now
- only rename frontend local state and presentation

Pros:

- narrower UI-only touch

Cons:

- likely fake progress
- leaves the actual API contract still lease-shaped

## Recommendation

Prefer Candidate 1.

Reason:

- replay-22 is specifically about outward contract cleanup
- cleaning only UI wording while keeping the API contract lease-shaped would
  mostly be cosmetic

## Proposed First Implementation Checkpoint After Replay-22

`database-refactor-dev-replay-23-request-and-frontend-launch-config-shell-contract-cleanup`

Likely boundary:

- `backend/web/models/requests.py`
- backend router/request serialization only as needed
- `frontend/app/src/api/client.ts`
- `frontend/app/src/api/types.ts`
- `frontend/app/src/pages/NewChatPage.tsx`
- focused frontend/API tests

## Stopline

Replay-22 does **not** authorize:

- runtime/resource/monitor surface changes
- storage contract changes
- backend thread binding logic changes
- SQL/migrations/live DB writes
- historical row repair
- broad product redesign outside launch-config/thread-create shell

## Open Question For Ledger Ruling

Is replay-22 the right checkpoint to classify the remaining outward shell
contract as the next residue target, and should the next implementation slice
prefer a combined request/frontend contract cleanup rather than a UI-only or
backend-only half step?
