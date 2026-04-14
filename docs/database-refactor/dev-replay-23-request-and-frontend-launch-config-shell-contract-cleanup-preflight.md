# Database Refactor Dev Replay 23: Request And Frontend Launch Config Shell Contract Cleanup Preflight

## Goal

Define the first implementation slice that cleans the remaining outward shell
contract for thread-create / launch-config selection by replacing shell-level
`lease_id` naming with `existing_sandbox_id`.

This checkpoint is preflight only. It does not implement the rename yet.

## Why This Comes Next

Replay-22 already closed the design question:

- the remaining residue is outward shell naming and payload shape
- backend-shell truth is already clean enough
- runtime/resource `lease_id` identity must stay out of lane

That means replay-23 should stop debating the direction and instead define the
exact synchronized request/frontend cleanup slice.

## Current Code Facts

### 1. Backend request models still expose shell-level `lease_id`

`backend/web/models/requests.py` still defines:

- `CreateThreadRequest.lease_id`
- `SaveThreadLaunchConfigRequest.lease_id`

These are not runtime/resource identity fields. They are outward shell entry
points for choosing an existing sandbox.

### 2. Frontend API contract still exposes shell-level `lease_id`

`frontend/app/src/api/client.ts` still includes:

- `CreateThreadOptions.leaseId`
- `createThread(...)` writing `body.lease_id`
- `parseThreadLaunchConfig(...)` reading `payload.lease_id`

`frontend/app/src/api/types.ts` still includes:

- `ThreadLaunchConfig.lease_id?: string | null`

These are the public frontend contract surfaces that still speak the old shell
name.

### 3. Frontend orchestration state is still lease-shaped

`frontend/app/src/hooks/use-thread-manager.ts` still exposes:

- `handleCreateThread(..., leaseId?: string, ...)`

`frontend/app/src/pages/NewChatPage.tsx` still uses:

- `selectedLeaseId`
- `config.lease_id`
- `saveDefaultThreadConfig(... lease_id: ...)`
- existing-mode create path passing `selectedLease.lease_id`

So the shell residue is not isolated to one component. It spans request model,
API client/types, thread-manager helper, and page state.

### 4. Not every `lease_id` is shell residue

These remain legitimate runtime/resource identity and are out of lane:

- `UserLeaseSummary.lease_id`
- `TerminalStatus.lease_id`
- `LeaseStatus.lease_id`
- `parseUserLeases(...)`
- `parseTerminalStatus(...)`
- `parseLeaseStatus(...)`
- backend monitor/runtime/resource surfaces that address real leases

Replay-23 must not rename or reinterpret any of those.

## Chosen Naming Direction

Replay-23 should use:

- `existing_sandbox_id`

Reason:

- it matches the user-facing shell action: choose an existing sandbox
- it stops presenting the selector as native runtime lease truth
- it is narrower and less misleading than generic names like `sandbox_id`
- it keeps create-mode semantics explicit: this field belongs to the existing
  branch of the launch shell

## Exact Target

Replay-23 should make the outward shell contract consistent around
`existing_sandbox_id`:

- backend request models accept `existing_sandbox_id`
- frontend API client/types use `existingSandboxId` / `existing_sandbox_id`
- frontend local state uses `selectedExistingSandboxId`
- default launch-config serialization/parsing uses `existing_sandbox_id`

The runtime/resource model beneath that contract does **not** change:

- existing-mode create still resolves/binds the selected live lease row
- saved canonical existing-mode config may still be rebuilt from the selected
  lease row under current backend truth

So this is a shell cleanup slice, not a runtime rewrite.

## Exact Write Set

### Authorized backend code

- `backend/web/models/requests.py`
- `backend/web/routers/threads.py`

`threads.py` is in-lane because request parsing and route-level save/create
payload handling need to move in lockstep with the request model rename.

### Authorized frontend code

- `frontend/app/src/api/client.ts`
- `frontend/app/src/api/types.ts`
- `frontend/app/src/hooks/use-thread-manager.ts`
- `frontend/app/src/pages/NewChatPage.tsx`

### Authorized focused tests

- `tests/Integration/test_thread_launch_config_contract.py`
- `tests/Integration/test_threads_router.py`
- `frontend/app/src/api/client.test.ts`
- `frontend/app/src/pages/NewChatPage.test.tsx`

### Out of lane even if grep finds `lease_id`

- monitor/resource/runtime routes and tests
- sandbox lease list/detail types beyond shell launch-config parsing
- terminal/lease status contracts
- storage/runtime bindings
- SQL/migrations/live DB writes

## Planned Mechanism

Replay-23 should prefer one synchronized rename slice instead of aliases.

### Backend request side

Rename:

- `CreateThreadRequest.lease_id` -> `CreateThreadRequest.existing_sandbox_id`
- `SaveThreadLaunchConfigRequest.lease_id` ->
  `SaveThreadLaunchConfigRequest.existing_sandbox_id`

Then update route code so request handling reads the new field name while still
resolving/binding the same underlying owned lease row.

### Frontend API/types side

Rename:

- `CreateThreadOptions.leaseId` -> `CreateThreadOptions.existingSandboxId`
- `ThreadLaunchConfig.lease_id` -> `ThreadLaunchConfig.existing_sandbox_id`
- serializer/parser payload keys to `existing_sandbox_id`

### Frontend orchestration/page side

Rename:

- `handleCreateThread(... leaseId ...)` -> `handleCreateThread(... existingSandboxId ...)`
- `selectedLeaseId` -> `selectedExistingSandboxId`

Keep the actual selected object source as the existing lease list for now.
Replay-23 is not required to rename `UserLeaseSummary` or the live lease list
API because those still model real runtime/resource identity.

## No Long-Lived Alias Rule

Replay-23 should **not** introduce a long-lived bilingual shell contract like:

- request accepts both `lease_id` and `existing_sandbox_id`
- frontend sends one but reads both forever

If a microscopic compatibility shim is required to keep one focused test or one
route path honest during the same slice, it must be:

- internal only
- short-lived
- removed before calling the checkpoint done

The target state of replay-23 is one outward shell name, not two.

## Test Plan

Replay-23 should be driven by focused contract tests, not broad product work.

Required proof:

1. backend request models and route tests accept `existing_sandbox_id` and no
   longer rely on shell-level `lease_id`
2. create-thread existing-mode route path still binds the selected existing
   sandbox correctly
3. default-config route save/load paths serialize and parse
   `existing_sandbox_id`
4. frontend API client serializes `existingSandboxId` to
   `existing_sandbox_id`
5. frontend launch-config parsing returns `existing_sandbox_id`
6. `NewChatPage` existing-mode flow still passes the selected existing sandbox
   through the helper layer using the new shell name

Not required in replay-23:

- YATU frontend/browser proof
- runtime/provider proof
- migration proof

## Stopline

Replay-23 must not:

- rename runtime/resource lease identity surfaces
- change `UserLeaseSummary.lease_id`
- change `TerminalStatus.lease_id`
- change `LeaseStatus.lease_id`
- change monitor/resource APIs
- change backend thread binding truth
- change storage contracts
- add SQL/migrations/live DB writes
- redesign the existing-sandbox chooser UX

## Expected Artifact

If replay-23 lands cleanly, the result should be simple to state:

- outward shell contract now says `existing_sandbox_id`
- runtime/resource surfaces still say `lease_id`
- there is no permanent dual-name shell contract left behind

## Open Question For Ledger Ruling

Is this the right replay-23 implementation boundary:

- use `existing_sandbox_id` as the single outward shell name
- update backend request models, frontend API/types, `use-thread-manager`, and
  `NewChatPage` together
- keep runtime/resource `lease_id` surfaces untouched
- avoid long-lived request/frontend alias sprawl?
