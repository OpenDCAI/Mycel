# Database Refactor Dev Replay 15: Launch Config Backend Default Resolution Preflight

## Goal

Define the exact implementation boundary for the first backend-only cleanup
slice after replay-14:

- stop derived launch-config defaults from using lease-first coincidence as
  their native truth
- keep the current request shell, frontend payload shape, and runtime cutover
  out of scope

This checkpoint is preflight only. It does not implement the cleanup.

## Linkage

- replay-13 made supported thread-create paths write a concrete bridge into
  `thread.current_workspace_id`
- replay-14 closed the contract debate:
  - launch-config persistence is metadata, not authority
  - `lease_id` is tolerated only as ingress / round-trip residue
  - the next implementation slice should be backend-only default-resolution
    cleanup

## Current Truth

Today `backend/web/services/thread_launch_config_service.py` resolves defaults
in this order:

1. validate `last_successful`
2. validate `last_confirmed`
3. derive a fresh config by:
   - listing agent threads
   - listing live user leases
   - picking the first lease whose `thread_ids` intersects those thread ids

That third step is the remaining mismatch. It still treats lease-thread
association as the backend's native authority, even though replay-13 already
moved create-time thread truth to `current_workspace_id`.

## Required Direction

Replay-15 should change only the backend default-resolution logic.

The target rule is:

```text
agent threads -> thread-owned current_workspace_id -> matching live bridge ->
existing config
```

Not:

```text
agent threads -> intersect thread_ids inside live leases -> existing config
```

This still allows a narrow temporary residue:

- the returned `"existing"` config may continue to carry `lease_id`
- saved launch-config payloads may remain lease-shaped

But that `lease_id` must now be downstream metadata derived from the
thread-owned bridge, not the source of truth used to discover the bridge.

## Exact Write Set

### Authorized code

- `backend/web/services/thread_launch_config_service.py`

### Authorized tests

- `tests/Integration/test_thread_launch_config_contract.py`

### Explicitly out of scope

- `backend/web/models/requests.py`
- `backend/web/routers/threads.py`
- `frontend/app/src/api/client.ts`
- `frontend/app/src/pages/NewChatPage.tsx`
- `storage/contracts.py`
- `storage/providers/supabase/thread_launch_pref_repo.py`
- any runtime/monitor/file-channel/schedule code
- any SQL or live DB write

## Planned Mechanism

Replay-15 should keep the outer API shape unchanged and only tighten
`resolve_default_config(...)` / `_derive_default_config(...)`.

The intended mechanism is:

1. read `agent_threads = thread_repo.list_by_agent_user(agent_user_id)`
2. identify candidate thread rows that already carry a non-blank
   `current_workspace_id`
3. choose the most defensible candidate from thread truth rather than from
   lease coincidence
4. look up the matching live lease using that thread-owned bridge id
5. if the live bridge is still resolvable, emit `"existing"` config from that
   bound resource
6. otherwise fall back to the existing provider/recipe-based `"new"` default

This means replay-15 still tolerates live-lease lookup as a materialization
step, but no longer as the discovery authority.

## Candidate Selection Rule

Replay-15 should keep candidate selection simple.

The preferred rule is:

- scan agent threads in descending recency if timestamps are available
- otherwise preserve current repo return order
- pick the first thread row whose `current_workspace_id` is non-blank and can
  still be materialized to a live lease

Do not invent scoring, ranking, or multi-thread heuristics in this slice.

## Test Plan

Replay-15 should be driven by focused contract tests in
`tests/Integration/test_thread_launch_config_contract.py`.

Required RED/GREEN coverage:

1. when saved configs are absent/invalid, derived default should use
   `thread.current_workspace_id` rather than `lease.thread_ids` intersection
2. a lease with matching `thread_ids` but no matching
   `current_workspace_id` bridge must not win
3. if a thread-owned bridge points to a missing live lease, derivation should
   fall back cleanly to the existing `"new"` provider/recipe default
4. saved `last_successful` / `last_confirmed` precedence should remain intact

No product-level YATU is required for replay-15 preflight itself. This is a
mechanism-layer slice.

## Stopline

Replay-15 must not:

- redesign request payloads
- remove `lease_id` from the create/config shell
- change `save_last_confirmed_config(...)` or `save_last_successful_config(...)`
  payload shape unless strictly required by the backend-only default-resolution
  cleanup
- modify thread creation flow
- touch frontend behavior
- cut runtime over to a new binding reader
- add migrations, schema work, or live DB writes
- add fallback-heavy heuristics

## Expected Artifact

If replay-15 is authorized, the result should be a narrow backend PR whose
effect is easy to state:

- derived default resolution now follows thread-owned bridge truth
- saved shell payloads remain temporarily lease-shaped
- no outward shell/runtime contract was widened

## Open Question To Resolve In The Ruling

Is replay-15 allowed to keep emitted `"existing"` defaults carrying `lease_id`
as frontend-facing residue while switching backend discovery authority to
`current_workspace_id`?

The intended answer is yes, because replay-14 already allowed `lease_id` as
ingress / round-trip residue. Replay-15 just must not continue to use it as the
native backend discovery key.
