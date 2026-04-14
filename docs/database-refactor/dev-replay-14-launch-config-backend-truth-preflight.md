# Database Refactor Dev Replay 14: Launch Config Backend Truth Preflight

## Goal

Define the minimal truthful backend contract for launch-config persistence and
default resolution after replay-13 landed create-time
`thread.current_workspace_id`.

This checkpoint is doc/ruling only. It does not implement backend behavior
changes, frontend changes, request-shell redesign, runtime cutover,
file-channel/monitor/schedule work, SQL/migrations, live DB writes, or legacy
deletion.

## Linkage

- replay-12 declared launch-config persistence as explicit residue after the
  thread write contract was clarified
- replay-13 made supported thread-create paths write a concrete bridge into
  `thread.current_workspace_id`
- current mismatch: backend launch-config persistence and default derivation are
  still lease-centric, even though thread creation truth now lands on
  `current_workspace_id`

## Architectural Frame

The product/runtime concept remains:

```text
thread -> sandbox
workspace = a thin workdir inside that sandbox
```

The currently persisted bridge remains:

```text
thread.current_workspace_id -> workspace -> sandbox
```

Replay-14 is not about changing that architecture. It is about deciding how the
backend launch-config layer should speak truthfully now that replay-13 has
already landed the thread-side bridge.

## Sources

- `docs/database-refactor/dev-replay-12-thread-create-write-contract-preflight.md`
- `backend/web/services/thread_launch_config_service.py`
- `backend/web/models/requests.py`
- `backend/web/routers/threads.py`
- `storage/contracts.py`
- `storage/providers/supabase/thread_repo.py`
- `frontend/app/src/api/client.ts`
- `frontend/app/src/pages/NewChatPage.tsx`

## Current Code Facts

### 1. Persisted launch-config payload is still lease-shaped

`backend/web/services/thread_launch_config_service.py:12-20` normalizes stored
payload into:

- `create_mode`
- `provider_config`
- `recipe_id`
- `lease_id`
- `model`
- `workspace`

There is no persisted `current_workspace_id`, sandbox binding id, or other
thread-aligned runtime pointer in this payload shape.

`backend/web/models/requests.py:27-34` matches that lease-shaped persistence
surface:

- `SaveThreadLaunchConfigRequest.lease_id` still exists
- no workspace-id field exists

### 2. Saved "existing" config is validated by live lease lookup

`backend/web/services/thread_launch_config_service.py:100-121` treats an
`existing` config as valid only if:

- `lease_id` is present
- `lease_id` resolves inside `sandbox_service.list_user_leases(...)`

If the lease disappears, the saved config is discarded.

This means backend launch-config persistence currently treats the lease list as
its authority surface for `"existing"`, not thread rows and not
`current_workspace_id`.

### 3. Derived default config is still agent-lease-first

`backend/web/services/thread_launch_config_service.py:162-176` derives default
config by:

- collecting all agent thread ids from `thread_repo.list_by_agent_user(...)`
- scanning live user leases
- picking the first lease whose `thread_ids` intersects those agent thread ids
- returning `_existing_config_from_lease(...)`

So the current derived-default rule is:

```text
agent threads -> intersect live leases -> choose lease -> emit existing config
```

Not:

```text
agent threads -> inspect thread.current_workspace_id -> resolve binding -> emit config
```

### 4. Thread create success persistence still writes lease semantics on existing path

`backend/web/routers/threads.py:651-699` now writes
`current_workspace_id` during thread creation, but it still persists
last-successful launch config as:

- existing path: `build_existing_launch_config(lease=owned_lease, ...)`
- new path: `build_new_launch_config(...)`

So replay-13 corrected thread-row write truth, but not launch-config persistence
truth.

### 5. Frontend shell is still lease-centric, but replay-14 does not touch it

Frontend still sends and restores `lease_id`:

- `frontend/app/src/api/client.ts`
- `frontend/app/src/pages/NewChatPage.tsx`

This matters because it constrains what the backend may reject today. But it is
not authorization to keep backend internals dual-authority forever.

## Contract Mismatch

After replay-13, the backend now has two different truth surfaces:

1. **Thread creation truth**
   - supported create paths write `thread.current_workspace_id`

2. **Launch-config truth**
   - saved config persistence still keys `"existing"` off `lease_id`
   - derived defaults still scan live leases first

That duality is the residue replay-14 must name precisely.

## Ruling

### 1. Launch-config persistence is metadata, not authority

The backend launch-config layer must not define runtime truth on its own.

Its role is:

- remember recent user/operator choices
- validate whether those choices are still actionable
- provide a default draft for the create UI

Its role is **not**:

- declare the authoritative thread binding model
- outvote thread-row write truth
- keep lease-first semantics alive after thread-side truth has changed

### 2. `lease_id` remains tolerated only as ingress metadata for the current shell

Explicit temporary treatment:

- tolerated:
  - `CreateThreadRequest.lease_id`
  - `SaveThreadLaunchConfigRequest.lease_id`
  - stored `last_confirmed` / `last_successful` payloads that still carry
    `lease_id`
  - backend validation of that saved shell payload against live leases

- not tolerated:
  - any new storage/thread binding seam using `lease_id` as authoritative truth
  - any claim that saved launch-config persistence is the system-of-record for
    runtime binding
  - any widening of `lease_id` deeper into thread repo/runtime contracts

This is ingress tolerance only. It is not architectural endorsement.

### 3. Derived backend defaults should stop being lease-first in the next implementation slice

The first replay-14 implementation slice should target backend default
resolution, not frontend payload cleanup.

Required direction:

- backend default resolution should prefer thread-aligned truth
- specifically, it should stop deriving `"existing"` defaults purely by
  intersecting agent threads with live leases
- if `"existing"` remains supported, its backend derivation must be justified by
  thread-owned binding truth, not lease-list coincidence

This does **not** force a request-shell cut in replay-14. It only says the
backend read/persistence layer must stop treating lease-first derivation as its
native truth.

### 4. Saved launch-config payload may remain lease-shaped for one narrow follow-up slice

Replay-14 does not require immediate removal of `lease_id` from saved payloads.

But the only legal reason to keep it temporarily is:

- the current frontend shell still submits `"existing"` choices in lease terms
- the backend still needs to round-trip that draft faithfully during the
  cleanup transition

That temporary legality ends where backend truth begins:

- thread creation truth already moved
- next backend launch-config slice must follow it

No vague "transition period" language is allowed beyond this explicit residue.

### 5. Replay-14 does not authorize frontend or runtime cutover

This preflight does **not** authorize:

- removing `lease_id` from frontend payloads
- redesigning `NewChatPage`
- changing runtime binding readers/managers
- changing file-channel/monitor/schedule semantics
- migrations or live DB writes

Those are separate checkpoints.

## Proposed First Implementation Checkpoint After Replay-14

`database-refactor-dev-replay-15-launch-config-backend-default-resolution`

Target boundary:

- keep request shell unchanged
- keep frontend unchanged
- keep thread create contract unchanged
- change backend launch-config resolution so derived defaults no longer use
  lease-first coincidence as native truth
- explicitly document whether saved `lease_id` remains round-trip metadata or is
  replaced by a thread-aligned backend representation

## Stopline

Replay-14 does **not** authorize:

- frontend product changes
- request model redesign
- runtime cutover
- monitor/file-channel/schedule work
- SQL/migrations/live DB writes
- legacy deletion outside the narrow backend launch-config slice

## Honest Residuals

- saved launch-config payloads are still lease-shaped
- backend validates `"existing"` configs through live lease lookup
- backend derived defaults are still agent-lease-first
- frontend shell is still lease-centric

Those residuals are now explicit. The next slice must reduce backend
dual-authority, not bury it under more lease-aware glue.
